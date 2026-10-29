"""Run the same agent task through Path A (plain REST-to-MCP) and Path B
(Apollo MCP Server -> router -> Connectors) and record what reached the model.

The agent is scripted: it makes the tool calls a model would need, in a fixed
order, so every number reproduces without a model or an API key. Both paths
must reach the same decision; the harness checks that.

Token counts are estimates: characters / 4, the same estimate the Apollo MCP
Server prints for its own tool definitions. They are for comparing A with B,
not for billing.

Usage: uv run python -m agent.harness   (needs services, router and MCP server up; see README)
"""

import asyncio
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import MCPError
from mcp.client.streamable_http import streamable_http_client

from services.seed import PII_EMAIL, PII_PHONE

CAMPAIGN = "cmp-acme-q4"
SERVICES = {"media": 4101, "ads": 4102, "crm": 4103}
APOLLO_MCP = "http://127.0.0.1:8000/mcp"
ROUTER = "http://localhost:4000/"
ROOT = Path(__file__).resolve().parents[1]
PII = [PII_EMAIL, PII_PHONE, "Jordan Lee", "100 Example Ave"]
QUIET = open(os.devnull, "w")  # the baseline servers log every REST call to stderr


def est_tokens(chars: int) -> int:
    return round(chars / 4)


def reset_services():
    httpx.post(f"http://127.0.0.1:{SERVICES['ads']}/_reset", timeout=5)


def rest_calls() -> dict:
    out = {}
    for name, port in SERVICES.items():
        out[name] = httpx.get(f"http://127.0.0.1:{port}/_calls", timeout=5).json()["count"]
    out["total"] = sum(out.values())
    return out


class Recorder:
    """Wraps an MCP session and records every call and what it returned."""

    def __init__(self, session: ClientSession):
        self.s = session
        self.calls = []

    async def tools(self):
        listed = (await self.s.list_tools()).tools
        defs = json.dumps([t.model_dump(exclude_none=True) for t in listed])
        return [t.name for t in listed], len(defs)

    async def call(self, name: str, args: dict):
        try:
            res = await self.s.call_tool(name, args)
        except MCPError as e:  # the server refused the call itself, e.g. an unlisted tool
            self.calls.append({"tool": name, "chars": 0, "error": True})
            return f"MCPError: {e}", True
        text = "".join(getattr(c, "text", "") for c in res.content)
        self.calls.append({"tool": name, "chars": len(text), "error": bool(res.is_error)})
        return text, bool(res.is_error)

    def summary(self):
        chars = sum(c["chars"] for c in self.calls)
        return {"mcp_calls": len(self.calls), "chars_returned": chars, "est_tokens_returned": est_tokens(chars)}


def decide(rows):
    """The agent's reasoning, identical on both paths: move 5,000 from the worst
    cost per conversion to the best. rows: [(line_item_id, segment_name, spend, conversions)]"""
    cpa = sorted(((spend / conv, li, seg) for li, seg, spend, conv in rows), key=lambda r: r[0])
    best, worst = cpa[0], cpa[-1]
    return {"from": worst[1], "to": best[1], "amount": 5000.0,
            "reason": f"CPA ${worst[0]:.0f} on {worst[2]} vs ${best[0]:.0f} on {best[2]}"}


def pii_hits(texts) -> list:
    blob = " ".join(texts)
    return [p for p in PII if p in blob]


async def run_path_a() -> dict:
    params = StdioServerParameters(command="uv", args=["run", "python", "-m", "baseline.rest_mcp"], cwd=str(ROOT))
    async with stdio_client(params, errlog=QUIET) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        rec = Recorder(s)
        names, def_chars = await rec.tools()
        reset_services()
        texts = []
        camp, _ = await rec.call("get_campaign", {"campaign_id": CAMPAIGN}); texts.append(camp)
        items, _ = await rec.call("list_line_items", {"campaign_id": CAMPAIGN}); texts.append(items)
        rows = []
        for li in json.loads(items):
            seg, _ = await rec.call("get_segment", {"segment_id": li["segmentId"]}); texts.append(seg)
            rows.append((li["id"], json.loads(seg)["name"], li["spend"], li["conversions"]))
        move = decide(rows)
        prop, _ = await rec.call("create_proposal", {"campaign_id": CAMPAIGN, "from_line_item_id": move["from"],
                                                     "to_line_item_id": move["to"], "amount": move["amount"],
                                                     "reason": move["reason"]}); texts.append(prop)
        adv, _ = await rec.call("get_advertiser", {"advertiser_id": json.loads(camp)["advertiserId"]}); texts.append(adv)
        owner = json.loads(adv)["accountOwner"]
        task = {**rec.summary(), "rest_calls": rest_calls(), "pii_reaching_model": pii_hits(texts)}
        # Scenario 5: the agent tries to move money without approval.
        _, err = await rec.call("set_budget", {"line_item_id": move["from"], "budget": 0})
        return {"tools": names, "tool_definition_chars": def_chars,
                "est_tokens_tool_definitions": est_tokens(def_chars), "task": task,
                "decision": {**move, "owner": owner}, "unapproved_write": "rejected" if err else "succeeded"}


async def run_path_a_prime() -> dict:
    params = StdioServerParameters(command="uv", args=["run", "python", "-m", "baseline.purpose_mcp"], cwd=str(ROOT))
    async with stdio_client(params, errlog=QUIET) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        rec = Recorder(s)
        names, def_chars = await rec.tools()
        reset_services()
        texts = []
        perf, _ = await rec.call("campaign_performance", {"campaign_id": CAMPAIGN}); texts.append(perf)
        rows = [(li["id"], li["segment"]["name"], li["spend"], li["conversions"]) for li in json.loads(perf)["lineItems"]]
        move = decide(rows)
        prop, _ = await rec.call("propose_budget_move", {"campaign_id": CAMPAIGN, "from_line_item_id": move["from"],
                                                         "to_line_item_id": move["to"], "amount": move["amount"],
                                                         "reason": move["reason"]}); texts.append(prop)
        own, _ = await rec.call("account_owner", {"campaign_id": CAMPAIGN}); texts.append(own)
        owner = json.loads(own)["accountOwner"]
        task = {**rec.summary(), "rest_calls": rest_calls(), "pii_reaching_model": pii_hits(texts)}
        return {"tools": names, "tool_definition_chars": def_chars,
                "est_tokens_tool_definitions": est_tokens(def_chars), "task": task,
                "decision": {**move, "owner": owner},
                "apply_tool_listed": any("budget" in n and "propose" not in n for n in names)}


async def run_path_b() -> dict:
    async with streamable_http_client(APOLLO_MCP) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        rec = Recorder(s)
        names, def_chars = await rec.tools()
        reset_services()
        texts = []
        perf, err = await rec.call("CampaignPerformance", {"campaignId": CAMPAIGN}); texts.append(perf)
        if err:
            raise RuntimeError(f"CampaignPerformance failed: {perf}")
        data = json.loads(perf)["data"]["campaign"]
        rows = [(li["id"], li["segment"]["name"], li["spend"], li["conversions"]) for li in data["lineItems"]]
        move = decide(rows)
        prop, _ = await rec.call("ProposeBudgetMove", {"campaignId": CAMPAIGN, "fromLineItemId": move["from"],
                                                       "toLineItemId": move["to"], "amount": move["amount"],
                                                       "reason": move["reason"]}); texts.append(prop)
        own, _ = await rec.call("AccountOwner", {"campaignId": CAMPAIGN}); texts.append(own)
        owner = json.loads(own)["data"]["campaign"]["advertiser"]["accountOwner"]
        task = {**rec.summary(), "rest_calls": rest_calls(), "pii_reaching_model": pii_hits(texts)}
        # Scenario 3: the agent asks for a tool that was never listed (ad-hoc GraphQL).
        adhoc, adhoc_err = await rec.call("execute", {"query": "{ campaign(id: \"cmp-acme-q4\") { advertiser { contactEmail } } }"})
        return {"tools": names, "tool_definition_chars": def_chars,
                "est_tokens_tool_definitions": est_tokens(def_chars), "task": task,
                "decision": {**move, "owner": owner},
                "apply_tool_listed": any("apply" in n.lower() for n in names),
                "adhoc_query": "refused" if adhoc_err else "answered", "adhoc_response": adhoc[:200]}


def router_checks() -> dict:
    """Scenarios 4 and 5 at the router, bypassing the MCP server: what does the
    agent's own token get if it calls the graph directly?"""
    out = {}
    for who in ("agent", "human"):
        tok_file = ROOT / "auth" / f"{who}.jwt"
        if not tok_file.exists():
            return {"skipped": "no tokens; run python -m auth.tokens"}
        h = {"Authorization": f"Bearer {tok_file.read_text().strip()}"}
        pii = httpx.post(ROUTER, headers=h, timeout=10, json={"query": '{ campaign(id: "cmp-acme-q4") { advertiser { accountOwner contactEmail contactPhone } } }'}).json()
        reset_services()
        prop = httpx.post(ROUTER, headers=h, timeout=10, json={"query": 'mutation { proposeBudgetMove(campaignId: "cmp-acme-q4", fromLineItemId: "li-4", toLineItemId: "li-5", amount: 1000, reason: "router check") { id } }'}).json()
        pid = ((prop.get("data") or {}).get("proposeBudgetMove") or {}).get("id")
        apply = httpx.post(ROUTER, headers=h, timeout=10, json={"query": f'mutation {{ applyBudgetMove(proposalId: "{pid or "none"}") {{ id status }} }}'}).json()
        ads_log = httpx.get(f"http://127.0.0.1:{SERVICES['ads']}/_calls", timeout=5).json()["calls"]
        out[who] = {"pii_query": pii, "apply": apply,
                    "apply_reached_ads_service": any(c.endswith("/apply") for c in ads_log)}
    return out


async def tool_names() -> list:
    async with streamable_http_client(APOLLO_MCP) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        return sorted(t.name for t in (await s.list_tools()).tools)


async def wait_for_tool_count(n: int, timeout: float = 15.0) -> float:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if len(await tool_names()) == n:
            return round(time.monotonic() - start, 1)
        await asyncio.sleep(0.5)
    raise TimeoutError(f"tool count never reached {n}")


async def kill_switch() -> dict:
    """Scenario 7: remove one operation file while the MCP server runs, then restore it."""
    op = ROOT / "mcp" / "operations" / "ProposeBudgetMove.graphql"
    parked = Path(tempfile.mkdtemp()) / op.name
    before = await tool_names()
    shutil.move(op, parked)
    try:
        gone_after = await wait_for_tool_count(len(before) - 1)
        during = await tool_names()
    finally:
        shutil.move(parked, op)
    back_after = await wait_for_tool_count(len(before))
    return {"before": before, "during": during, "after": await tool_names(),
            "seconds_to_remove": gone_after, "seconds_to_restore": back_after}


def _errors(resp: dict) -> list:
    return [((e.get("extensions") or {}).get("code") or e.get("message", "")) for e in resp.get("errors") or []]


def expectations(r: dict) -> list:
    """Each claim the README makes, checked against this run. A failure is reported, not hidden."""
    a, ap, b, rc, ks = r["path_a"], r["path_a_prime"], r["path_b"], r["router"], r["kill_switch"]
    adv = lambda who: ((((rc[who]["pii_query"].get("data") or {}).get("campaign") or {}).get("advertiser")) or {})
    applied = lambda who: (((rc[who]["apply"].get("data") or {}).get("applyBudgetMove")) or {}).get("status")
    checks = [
        ("Same decision on A, A′ and B", r["same_decision"]),
        ("PII reached the model on A, and not on A′ or B",
         bool(a["task"]["pii_reaching_model"]) and not ap["task"]["pii_reaching_model"] and not b["task"]["pii_reaching_model"]),
        ("A's agent moved money without approval; B lists no apply tool",
         a["unapproved_write"] == "succeeded" and not b["apply_tool_listed"]),
        ("B refused a tool that was never listed", b["adhoc_query"] == "refused"),
        ("Router, agent token: contact fields null with an error; owner name returned",
         adv("agent").get("contactEmail") is None and adv("agent").get("contactPhone") is None
         and adv("agent").get("accountOwner") == "Priya Shah" and bool(_errors(rc["agent"]["pii_query"]))),
        ("Router, human token: contact fields returned",
         adv("human").get("contactEmail") == PII_EMAIL and adv("human").get("contactPhone") == PII_PHONE),
        ("Router, agent token: apply refused and never reached the ads service",
         applied("agent") != "applied" and not rc["agent"]["apply_reached_ads_service"]),
        ("Router, human token: apply succeeded", applied("human") == "applied" and rc["human"]["apply_reached_ads_service"]),
        ("Kill switch: tools went 3 → 2 → 3 with no restart",
         len(ks["before"]) == 3 and len(ks["during"]) == 2 and len(ks["after"]) == 3),
    ]
    return [{"claim": c, "pass": bool(ok)} for c, ok in checks]


async def main():
    os.makedirs(ROOT / "results", exist_ok=True)
    result = {"path_a": await run_path_a(), "path_a_prime": await run_path_a_prime(),
              "path_b": await run_path_b(), "router": router_checks(), "kill_switch": await kill_switch()}
    result["same_decision"] = (result["path_a"]["decision"] == result["path_a_prime"]["decision"]
                               == result["path_b"]["decision"])
    result["expectations"] = expectations(result)
    (ROOT / "results" / "run.json").write_text(json.dumps(result, indent=2))
    for p in ("path_a", "path_a_prime", "path_b"):
        r = result[p]
        print(p, "tools", len(r["tools"]), "| def tokens", r["est_tokens_tool_definitions"], "| task", r["task"])
    for e in result["expectations"]:
        print("PASS" if e["pass"] else "FAIL", e["claim"])
    return 0 if all(e["pass"] for e in result["expectations"]) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
