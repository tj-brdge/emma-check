from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from termscheck.audit import GENESIS, chain_hash, verify_chain
from termscheck.audit.log import canonical

pytestmark = pytest.mark.db
ROOT = Path(__file__).resolve().parents[2]


def full_pipeline(client, screened, dataset):
    d = next(x for x in dataset.defects if x.defect_id.startswith("D01"))
    pdf = (ROOT / "data" / "sample_os" / f"OS_{d.cusip}.pdf").read_bytes()
    r = client.post(f"/api/screen-runs/{screened['run']}/cusips/{d.cusip}/official-statement",
                    files={"file": ("os.pdf", pdf, "application/pdf")}).json()
    fid = r["finding"]["id"]
    client.post(f"/api/findings/{fid}/actions", json={"action": "annotate", "comment": "checked"})
    client.post(f"/api/findings/{fid}/actions", json={"action": "approve"})
    client.get("/api/exports/approved.csv")
    return fid


def test_every_step_is_logged_with_user(client, screened, dataset):
    client.post("/api/uploads/holdings", files={"file": ("bad.csv", "cusip\nX\n", "text/csv")})
    fid = full_pipeline(client, screened, dataset)
    events = list(reversed(client.get("/api/audit?limit=1000").json()))
    types = [e["event_type"] for e in events]
    assert types[:4] == ["upload.accepted"] * 3 + ["screen_run.completed"]
    for t in ("upload.rejected", "document.registered", "extraction.completed", "computation.created",
              "finding.created", "review.annotate", "review.approve", "export.approved_csv"):
        assert t in types, t
    assert types.index("computation.created") < types.index("finding.created") < types.index("review.approve")
    assert {e["actor"] for e in events} == {"test.reviewer"}
    run_ev = next(e for e in events if e["event_type"] == "screen_run.completed")
    assert run_ev["payload"]["flag_count"] == len(run_ev["payload"]["flags"]) > 0
    ex_ev = next(e for e in events if e["event_type"] == "extraction.completed")
    assert ex_ev["payload"]["citations"]["interest_type"] == {"page": 6, "status": "verified"}
    assert ex_ev["payload"]["prompt_version"] and ex_ev["payload"]["model_requested"]
    comp_ev = next(e for e in events if e["event_type"] == "computation.created")
    assert comp_ev["payload"]["outputs"]["unbooked_income_usd"] > 0 and comp_ev["payload"]["bondmath_version"]
    appr = next(e for e in events if e["event_type"] == "review.approve")
    assert appr["entity_id"] == str(fid) and appr["payload"]["to_status"] == "approved"
    assert all(e["ts"].endswith("+00:00") for e in events)


def test_chain_verifies_and_links(client, screened, dataset, db):
    full_pipeline(client, screened, dataset)
    v = client.get("/api/audit/verify").json()
    assert v["ok"] and v["checked"] > 10
    events = list(reversed(client.get("/api/audit?limit=1000").json()))
    assert events[0]["prev_hash"] == GENESIS
    for a, b in zip(events, events[1:]):
        assert b["prev_hash"] == a["hash"]
    e = events[3]
    assert chain_hash(e["prev_hash"], canonical(e["ts"], e["actor"], e["event_type"], e["entity_type"],
                                                e["entity_id"], e["payload"])) == e["hash"]


def _tamper(engine, sql):
    with engine.begin() as c:
        c.execute(text("SET LOCAL session_replication_role = replica"))  # superuser bypass, simulating an attacker
        c.execute(text(sql))


def test_tampering_is_detected(client, screened, dataset, engine, db):
    full_pipeline(client, screened, dataset)
    target = next(e for e in client.get("/api/audit?event_type=review.approve").json())
    _tamper(engine, f"UPDATE audit_event SET payload = jsonb_set(payload, '{{comment}}', '\"edited\"') WHERE id = {target['id']}")
    v = client.get("/api/audit/verify").json()
    assert not v["ok"] and v["first_bad_id"] == target["id"] and "hash" in v["reason"]


def test_deletion_is_detected(client, screened, dataset, engine, db):
    full_pipeline(client, screened, dataset)
    _tamper(engine, "DELETE FROM audit_event WHERE id = 5")
    v = client.get("/api/audit/verify").json()
    assert not v["ok"] and v["first_bad_id"] == 6 and "prev_hash" in v["reason"]


@pytest.mark.parametrize("table", ["audit_event", "review_action", "screen_flag", "screen_run", "extraction",
                                   "computation", "upload_batch", "document"])
def test_write_once_tables_reject_update_delete_truncate(client, screened, dataset, engine, table):
    full_pipeline(client, screened, dataset)
    for sql in (f"UPDATE {table} SET id = id WHERE id = (SELECT min(id) FROM {table})",
                f"DELETE FROM {table} WHERE id = (SELECT min(id) FROM {table})",
                f"TRUNCATE {table} CASCADE"):
        with pytest.raises(DBAPIError, match="append-only"):
            with engine.begin() as c:
                c.execute(text(sql))


def test_finding_only_status_may_change(client, screened, dataset, engine):
    fid = full_pipeline(client, screened, dataset)
    with engine.begin() as c:
        c.execute(text(f"UPDATE finding SET status = 'approved' WHERE id = {fid}"))
    for sql in (f"UPDATE finding SET income_impact_usd = 0 WHERE id = {fid}",
                f"UPDATE finding SET headline = 'x' WHERE id = {fid}",
                f"DELETE FROM finding WHERE id = {fid}"):
        with pytest.raises(DBAPIError):
            with engine.begin() as c:
                c.execute(text(sql))


def test_verify_chain_service_on_empty_log(db):
    c = verify_chain(db)
    assert c.ok and c.checked == 0
