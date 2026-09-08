from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert "endpoints" in r.json()


def test_policies():
    r = client.get("/policies")
    assert r.status_code == 200
    body = r.json()
    assert "NORMAL" in body["scenarios"]
    assert "NEAREST_DRIVER" in body["dispatch_policies"]


def test_simulation_run_and_fetch():
    r = client.post("/simulation/run", json={
        "scenario": "NORMAL", "pricing_policy": "BASIC_SURGE",
        "dispatch_policy": "NEAREST_DRIVER", "seed": 1, "hours": 2,
    })
    assert r.status_code == 200
    body = r.json()
    assert "run_id" in body
    assert body["summary"]["n_requests"] >= 0

    r2 = client.get(f"/simulation/{body['run_id']}")
    assert r2.status_code == 200
    assert r2.json()["run_id"] == body["run_id"]

    r3 = client.get(f"/simulation/{body['run_id']}/metrics")
    assert r3.status_code == 200
    assert "n_requests" in r3.json()


def test_simulation_run_rejects_bad_policy():
    r = client.post("/simulation/run", json={
        "scenario": "NORMAL", "pricing_policy": "NOT_A_POLICY",
        "dispatch_policy": "NEAREST_DRIVER", "seed": 0, "hours": 1,
    })
    assert r.status_code == 400


def test_get_unknown_run_404():
    r = client.get("/simulation/does-not-exist")
    assert r.status_code == 404


def test_experiments_endpoints():
    r = client.get("/experiments")
    assert r.status_code == 200
    assert r.json()["n_runs"] == 1080

    r2 = client.get("/experiments/decision_table")
    assert r2.status_code == 200
    assert len(r2.json()) == 20

    r3 = client.get("/experiments/not_a_report")
    assert r3.status_code == 404
