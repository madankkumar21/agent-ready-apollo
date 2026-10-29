"""Path A: a plain REST-to-MCP server, one tool per endpoint.

This is the shape an OpenAPI-to-MCP generator produces, and the shape I built
by hand at Coactive: each tool calls one REST endpoint and hands the model the
full response. The server holds one service credential, so every agent that
connects can call every tool, including the one that moves money.

Run over stdio: `uv run python -m baseline.rest_mcp`.
"""

import json

import httpx
from mcp.server.mcpserver import MCPServer

MEDIA, ADS, CRM = "http://127.0.0.1:4101", "http://127.0.0.1:4102", "http://127.0.0.1:4103"

mcp = MCPServer("rest-baseline")


def _get(url: str) -> str:
    r = httpx.get(url, timeout=10)
    r.raise_for_status()
    return json.dumps(r.json())


def _post(url: str, body: dict) -> str:
    r = httpx.post(url, json=body, timeout=10)
    r.raise_for_status()
    return json.dumps(r.json())


@mcp.tool()
def get_campaign(campaign_id: str) -> str:
    """Get a campaign by id."""
    return _get(f"{ADS}/campaigns/{campaign_id}")


@mcp.tool()
def list_line_items(campaign_id: str) -> str:
    """List a campaign's line items."""
    return _get(f"{ADS}/campaigns/{campaign_id}/line-items")


@mcp.tool()
def get_line_item(line_item_id: str) -> str:
    """Get one line item."""
    return _get(f"{ADS}/line-items/{line_item_id}")


@mcp.tool()
def get_segment(segment_id: str) -> str:
    """Get a contextual segment."""
    return _get(f"{MEDIA}/segments/{segment_id}")


@mcp.tool()
def get_advertiser(advertiser_id: str) -> str:
    """Get an advertiser record."""
    return _get(f"{CRM}/advertisers/{advertiser_id}")


@mcp.tool()
def create_proposal(campaign_id: str, from_line_item_id: str, to_line_item_id: str, amount: float, reason: str) -> str:
    """Record a budget-move proposal. Moves no money."""
    return _post(f"{ADS}/proposals", {"campaignId": campaign_id, "fromLineItemId": from_line_item_id,
                                      "toLineItemId": to_line_item_id, "amount": amount, "reason": reason})


@mcp.tool()
def set_budget(line_item_id: str, budget: float) -> str:
    """Set a line item's budget."""
    return _post(f"{ADS}/line-items/{line_item_id}/budget", {"budget": budget})


if __name__ == "__main__":
    mcp.run()
