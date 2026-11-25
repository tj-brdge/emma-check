import pytest

pytestmark = pytest.mark.db


def upload(client, kind, text, name="f.csv", vendor=None):
    data = {"vendor": vendor} if vendor else {}
    return client.post(f"/api/uploads/{kind}", files={"file": (name, text, "text/csv")}, data=data)


def test_upload_requires_user(client, synthetic_csvs):
    client.headers.pop("X-User")
    assert upload(client, "holdings", synthetic_csvs["holdings"]).status_code == 401


def test_rejected_file_ingests_nothing(client):
    r = upload(client, "holdings", "cusip,description\nX,Y\n")
    assert r.status_code == 422
    assert "nothing was ingested" in r.json()["detail"]["message"]
    assert client.get("/api/batches").json() == []


def test_end_to_end_upload_and_screen(client, synthetic_csvs, dataset, screen_result):
    ids = {}
    for kind in ("holdings", "vendor_secondary", "price_history"):
        r = upload(client, kind, synthetic_csvs[kind], name=f"{kind}.csv")
        assert r.status_code == 200, r.text
        ids[kind] = r.json()["batch"]["id"]
        assert r.json()["batch"]["uploaded_by"] == "test.reviewer"
    r = client.post("/api/screen-runs", json={
        "as_of": dataset.as_of.isoformat(), "holdings_batch_id": ids["holdings"],
        "secondary_batch_id": ids["vendor_secondary"], "history_batch_id": ids["price_history"]})
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["started_by"] == "test.reviewer" and run["finished_at"]
    got = {(f["cusip"], f["rule"]) for f in run["flags"]}
    assert got == {(f.cusip, f.rule) for f in screen_result.flags}
    for f in run["flags"]:
        assert f["inputs"] and f["computed"] and 0 <= f["severity"] <= 100
    assert client.get(f"/api/screen-runs/{run['id']}").json()["flag_count"] == len(got)


def test_screen_run_config_override_and_validation(client, synthetic_csvs, dataset):
    hid = upload(client, "holdings", synthetic_csvs["holdings"]).json()["batch"]["id"]
    r = client.post("/api/screen-runs", json={"as_of": "2026-11-30", "holdings_batch_id": hid,
                                              "config": {"peer_z_threshold": 2.5}})
    assert r.json()["config"]["peer_z_threshold"] == 2.5
    r = client.post("/api/screen-runs", json={"as_of": "2026-11-30", "holdings_batch_id": hid,
                                              "config": {"not_a_setting": 1}})
    assert r.status_code == 422
    r = client.post("/api/screen-runs", json={"as_of": "2026-11-30", "holdings_batch_id": hid,
                                              "secondary_batch_id": hid})
    assert r.status_code == 422
