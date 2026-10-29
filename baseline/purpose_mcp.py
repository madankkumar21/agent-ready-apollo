"""Path A-prime: a purpose-built REST-to-MCP server.

The fair comparison for Apollo is not Path A's one-tool-per-endpoint server but
this: three tools written by hand for this one task. `campaign_performance`
calls the REST APIs itself, joins them and returns only the fields the agent
needs. No PII leaves the server and there is no tool that moves money.

It matches Path B on what reaches the model. The difference is where the rules
live: here, in this server's code, for this one agent. Another agent, or the
same agent through another server, gets whatever its own author wrote. In
Path B the joins, the field rules and the write gate live in the graph, and the
router enforces them for every client.

Run over stdio: `uv run python -m baseline.purpose_mcp`.
"""

import json

import httpx
from mcp.server.mcpserver import MCPServer

MEDIA, ADS, CRM = "http://127.0.0.1:4101", "http://127.0.0.1:4102", "http://127.0.0.1:4103"

mcp = MCPServer("purpose-built")


def _get(url: str):
    r = httpx.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


@mcp.tool()
def campaign_performance(campaign_id: str) -> str:
    """Delivery for every line item in a campaign: budget, spend, conversions and the segment it buys."""
    camp = _get(f"{ADS}/campaigns/{campaign_id}")
    items = []
    for li in _get(f"{ADS}/campaigns/{campaign_id}/line-items"):
        seg = _get(f"{MEDIA}/segments/{li['segmentId']}")
        items.append({"id": li["id"], "budget": li["budget"], "spend": li["spend"],
                      "conversions": li["conversions"], "segment": {"name": seg["name"]}})
    return json.dumps({"id": camp["id"], "name": camp["name"], "lineItems": items})


@mcp.tool()
def propose_budget_move(campaign_id: str, from_line_item_id: str, to_line_item_id: str, amount: float, reason: str) -> str:
    """Record a proposal to move budget between two line items. Moves no money; a human applies it."""
    r = httpx.post(f"{ADS}/proposals", timeout=10, json={
        "campaignId": campaign_id, "fromLineItemId": from_line_item_id,
        "toLineItemId": to_line_item_id, "amount": amount, "reason": reason})
    r.raise_for_status()
    p = r.json()
    return json.dumps({"id": p["id"], "status": p["status"], "amount": p["amount"]})


@mcp.tool()
def account_owner(campaign_id: str) -> str:
    """The account owner to notify about a campaign's proposal. Name only."""
    adv = _get(f"{CRM}/advertisers/{_get(f'{ADS}/campaigns/{campaign_id}')['advertiserId']}")
    return json.dumps({"name": adv["name"], "accountOwner": adv["accountOwner"]})


if __name__ == "__main__":
    mcp.run()
