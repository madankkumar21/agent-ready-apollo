"""Three mock REST services: media (segments), ads (campaigns, line items,
proposals, budgets) and crm (advertisers).

They have no auth of their own; in this demo the caller in front of them
(Path A's MCP server or Path B's router) is the only thing that decides who
may call what. Each service records every request so the harness can count
REST calls per path. `/_calls` and `/_reset` are test hooks, not API.
"""

import copy
import itertools

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from services import seed


class State:
    def __init__(self):
        self.reset()

    def reset(self):
        self.line_items = seed.line_items()
        self.proposals: dict[str, dict] = {}
        self.ids = itertools.count(1)
        self.calls: list[str] = []


state = State()


def _app(name: str) -> FastAPI:
    app = FastAPI(title=f"{name} (mock)")

    @app.middleware("http")
    async def log_calls(request: Request, call_next):
        if not request.url.path.startswith("/_"):
            state.calls.append(f"{name} {request.method} {request.url.path}")
        return await call_next(request)

    @app.get("/_calls")
    def calls():
        mine = [c for c in state.calls if c.startswith(name + " ")]
        return {"count": len(mine), "calls": mine}

    @app.post("/_reset")
    def reset():
        state.reset()
        return {"ok": True}

    return app


# ---- media ---------------------------------------------------------------
media = _app("media")


@media.get("/segments")
def list_segments():
    return [seed.segment(s) for s in seed.SEGMENTS]


@media.get("/segments/{seg_id}")
def get_segment(seg_id: str):
    if seg_id not in seed.SEGMENTS:
        raise HTTPException(404, "segment not found")
    return seed.segment(seg_id)


# ---- ads -----------------------------------------------------------------
ads = _app("ads")


@ads.get("/campaigns/{cmp_id}")
def get_campaign(cmp_id: str):
    if cmp_id not in seed.CAMPAIGNS:
        raise HTTPException(404, "campaign not found")
    return seed.CAMPAIGNS[cmp_id]


@ads.get("/campaigns/{cmp_id}/line-items")
def list_line_items(cmp_id: str):
    if cmp_id not in seed.CAMPAIGNS:
        raise HTTPException(404, "campaign not found")
    return [li for li in state.line_items.values() if li["campaignId"] == cmp_id]


@ads.get("/line-items/{li_id}")
def get_line_item(li_id: str):
    if li_id not in state.line_items:
        raise HTTPException(404, "line item not found")
    return state.line_items[li_id]


class ProposalIn(BaseModel):
    campaignId: str
    fromLineItemId: str
    toLineItemId: str
    amount: float
    reason: str


@ads.post("/proposals", status_code=201)
def create_proposal(p: ProposalIn):
    for li in (p.fromLineItemId, p.toLineItemId):
        if li not in state.line_items:
            raise HTTPException(404, f"line item {li} not found")
    pid = f"prop-{next(state.ids)}"
    state.proposals[pid] = {"id": pid, "status": "pending", **p.model_dump()}
    return state.proposals[pid]


@ads.get("/proposals/{pid}")
def get_proposal(pid: str):
    if pid not in state.proposals:
        raise HTTPException(404, "proposal not found")
    return state.proposals[pid]


@ads.post("/proposals/{pid}/apply")
def apply_proposal(pid: str):
    """Moves the money. Only a human should be able to reach this."""
    p = state.proposals.get(pid)
    if not p:
        raise HTTPException(404, "proposal not found")
    if p["status"] != "pending":
        raise HTTPException(409, f"proposal is {p['status']}")
    state.line_items[p["fromLineItemId"]]["budget"] -= p["amount"]
    state.line_items[p["toLineItemId"]]["budget"] += p["amount"]
    p["status"] = "applied"
    return p


class BudgetIn(BaseModel):
    budget: float


@ads.post("/line-items/{li_id}/budget")
def set_budget(li_id: str, b: BudgetIn):
    """Sets a budget directly, with no proposal. Path A exposes this as a tool."""
    if li_id not in state.line_items:
        raise HTTPException(404, "line item not found")
    state.line_items[li_id]["budget"] = b.budget
    return state.line_items[li_id]


# ---- crm -----------------------------------------------------------------
crm = _app("crm")


@crm.get("/advertisers/{adv_id}")
def get_advertiser(adv_id: str):
    if adv_id not in seed.ADVERTISERS:
        raise HTTPException(404, "advertiser not found")
    return copy.deepcopy(seed.ADVERTISERS[adv_id])


PORTS = {"media": 4101, "ads": 4102, "crm": 4103}
APPS = {"media": media, "ads": ads, "crm": crm}
