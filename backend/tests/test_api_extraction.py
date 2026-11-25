from pathlib import Path

import pytest

pytestmark = pytest.mark.db
ROOT = Path(__file__).resolve().parents[2]


def d(dataset, prefix):
    return next(x for x in dataset.defects if x.defect_id.startswith(prefix))


def upload_os(client, cusip):
    pdf = (ROOT / "data" / "sample_os" / f"OS_{cusip}.pdf").read_bytes()
    r = client.post("/api/documents", data={"cusip": cusip},
                    files={"file": (f"OS_{cusip}.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()


def test_document_extraction_finding_flow(client, screened, dataset):
    d01 = d(dataset, "D01")
    doc = upload_os(client, d01.cusip)
    assert doc["page_count"] == 11
    assert "Deferred Interest Bonds" in client.get(f"/api/documents/{doc['id']}/pages/6").json()["text"]
    assert client.get(f"/api/documents/{doc['id']}/file").content.startswith(b"%PDF")

    ex = client.post("/api/extractions", json={"document_id": doc["id"]}).json()
    assert ex["status"] == "ok" and ex["created_by"] == "test.reviewer"
    assert ex["interest_terms"]["interest_type"] == "deferred_interest"
    assert all(c["page"] for c in ex["citation_checks"] if c["status"] != "absent")

    f = client.post("/api/findings", json={"screen_run_id": screened["run"], "extraction_id": ex["id"]}).json()
    assert f["income_impact_usd"] > 1_000_000
    assert set(f["rules"]) >= {"yield_coupon_impossibility", "zero_coupon_sanity", "price_drift"}
    assert f["narrative"]["vendor_says"] and f["narrative"]["document_says"] and f["narrative"]["impact"]
    assert any(r["field"] == "Interest type" and r["page"] == 6 for r in f["comparison"])
    assert len(f["positions"]) == 1 and f["positions"][0]["computation_id"]


def test_findings_sorted_by_income_impact(client, screened, dataset):
    ids = []
    for p in ("D12", "D01"):
        doc = upload_os(client, d(dataset, p).cusip)
        ex = client.post("/api/extractions", json={"document_id": doc["id"]}).json()
        ids.append(client.post("/api/findings", json={"screen_run_id": screened["run"],
                                                      "extraction_id": ex["id"]}).json()["id"])
    listed = client.get("/api/findings").json()
    assert [x["cusip"] for x in listed] == [d(dataset, "D01").cusip, d(dataset, "D12").cusip]


def test_failed_extraction_recorded_and_blocks_finding(client, screened, dataset):
    # D01's OS uploaded under another CUSIP: the recording lookup fails -> extraction 'failed'.
    doc = upload_os(client, d(dataset, "D01").cusip)
    ex = client.post("/api/extractions", json={"document_id": doc["id"], "cusip": d(dataset, "D02").cusip}).json()
    assert ex["status"] == "failed" and ex["error"]
    r = client.post("/api/findings", json={"screen_run_id": screened["run"], "extraction_id": ex["id"]})
    assert r.status_code == 422


def test_non_pdf_rejected(client):
    r = client.post("/api/documents", data={"cusip": "FQ4TWLB23"}, files={"file": ("x.pdf", b"hello", "application/pdf")})
    assert r.status_code == 422
