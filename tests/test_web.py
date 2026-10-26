from fastapi.testclient import TestClient

from web.server import app


def test_api_run_short_scenario():
    c = TestClient(app)
    assert c.get("/").status_code == 200
    assert len(c.get("/api/modes").json()) == 10
    r = c.post("/api/run", json={"mode": "I_full_recovery",
                                 "scenario": {"horizon_s": 1800, "seed": 3, "source_loss_s": 900,
                                              "source_loss_nodes": ["F0_0"]}})
    assert r.status_code == 200
    d = r.json()
    assert len(d["timeline"]) == 30 and "CDR" in d["metrics"]
    assert any(e["type"] == "SOURCE_LOSS" for e in d["events"])
    assert c.post("/api/run", json={"mode": "nope"}).status_code == 400
