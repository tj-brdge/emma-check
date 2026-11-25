import csv
import io
from pathlib import Path

import pytest

from termscheck.review import ReviewError, Status, apply, replay

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- pure state machine
def test_transitions():
    assert apply("open", "approve", None) is Status.APPROVED
    assert apply("open", "reject", "credit event, terms are right") is Status.REJECTED
    assert apply("approved", "reopen", None) is Status.OPEN
    assert apply("approved", "annotate", "sent to ops") is Status.APPROVED


@pytest.mark.parametrize("status,action,comment", [
    ("approved", "approve", None), ("rejected", "approve", None), ("open", "reopen", None),
    ("open", "reject", None), ("open", "reject", "  "), ("open", "annotate", None),
])
def test_invalid_transitions(status, action, comment):
    with pytest.raises(ReviewError):
        apply(status, action, comment)


def test_unknown_action():
    with pytest.raises(ValueError):
        apply("open", "delete", None)


def test_replay_derives_status():
    assert replay([("approve", None), ("reopen", None), ("reject", "no"), ("annotate", "x")]) is Status.REJECTED


# ---------------------------------------------------------------- API
def make_finding(client, screened, dataset, prefix="D01"):
    d = next(x for x in dataset.defects if x.defect_id.startswith(prefix))
    pdf = (ROOT / "data" / "sample_os" / f"OS_{d.cusip}.pdf").read_bytes()
    r = client.post(f"/api/screen-runs/{screened['run']}/cusips/{d.cusip}/official-statement",
                    files={"file": ("os.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["error"] is None and body["extraction"]["status"] == "ok"
    return body["finding"]


@pytest.mark.db
def test_flagged_cusips_view(client, screened, dataset):
    body = client.get(f"/api/screen-runs/{screened['run']}/cusips").json()
    cusips = {c["cusip"] for c in body["cusips"]}
    assert dataset.defect_cusips <= cusips
    sev = [c["max_severity"] for c in body["cusips"]]
    assert sev == sorted(sev, reverse=True)
    make_finding(client, screened, dataset)
    d01 = next(x for x in dataset.defects if x.defect_id.startswith("D01")).cusip
    row = next(c for c in client.get(f"/api/screen-runs/{screened['run']}/cusips").json()["cusips"] if c["cusip"] == d01)
    assert row["finding_id"] and row["extraction_status"] == "ok" and row["income_impact_usd"] > 0


@pytest.mark.db
def test_review_flow_and_export(client, screened, dataset):
    f = make_finding(client, screened, dataset)
    fid = f["id"]
    assert client.post(f"/api/findings/{fid}/actions", json={"action": "reject"}).status_code == 422
    assert client.post(f"/api/findings/{fid}/actions", json={"action": "annotate", "comment": "checked p.6"}).json()["to_status"] == "open"
    a = client.post(f"/api/findings/{fid}/actions", json={"action": "approve", "comment": "agree, book accrual"}).json()
    assert a["from_status"] == "open" and a["to_status"] == "approved" and a["actor"] == "test.reviewer"
    assert client.post(f"/api/findings/{fid}/actions", json={"action": "approve"}).status_code == 422
    assert client.get(f"/api/findings/{fid}").json()["status"] == "approved"
    assert [x["action"] for x in client.get(f"/api/findings/{fid}/actions").json()] == ["annotate", "approve"]

    # a second, rejected finding must not be exported
    g = make_finding(client, screened, dataset, "D12")
    client.post(f"/api/findings/{g['id']}/actions", json={"action": "reject", "comment": "test"})

    r = client.get("/api/exports/approved.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 1
    row = rows[0]
    assert row["cusip"] == f["cusip"] and row["approved_by"] == "test.reviewer"
    assert row["document_interest_type"] == "deferred_interest" and row["vendor_coupon_pct"] == "0.0000"
    assert float(row["unbooked_income_usd"]) == pytest.approx(f["income_impact_usd"], abs=0.01)
    assert "interest_type p.6" in row["citations"]


@pytest.mark.db
def test_unknown_finding_404(client):
    assert client.post("/api/findings/999/actions", json={"action": "approve"}).status_code == 404
