from fastapi.testclient import TestClient

from services.app import ads, crm, media, state
from services.seed import PII_EMAIL


def setup_function():
    state.reset()


def test_segment_and_line_items():
    m, a = TestClient(media), TestClient(ads)
    assert m.get("/segments/seg-sports").json()["name"] == "Live sports moments"
    items = a.get("/campaigns/cmp-acme-q4/line-items").json()
    assert len(items) == 6 and {"spend", "conversions", "targeting"} <= items[0].keys()


def test_proposal_then_apply_moves_budget():
    a = TestClient(ads)
    p = a.post("/proposals", json={"campaignId": "cmp-acme-q4", "fromLineItemId": "li-4",
                                   "toLineItemId": "li-1", "amount": 5000, "reason": "test"}).json()
    assert p["status"] == "pending"
    assert a.get("/line-items/li-4").json()["budget"] == 20000  # a proposal moves nothing
    assert a.post(f"/proposals/{p['id']}/apply").json()["status"] == "applied"
    assert a.get("/line-items/li-4").json()["budget"] == 15000
    assert a.post(f"/proposals/{p['id']}/apply").status_code == 409


def test_crm_returns_pii_and_calls_are_counted():
    c = TestClient(crm)
    assert c.get("/advertisers/adv-acme").json()["contactEmail"] == PII_EMAIL
    assert c.get("/_calls").json()["count"] == 1
