"""Security and robustness controls."""
import csv
import io

import pytest

from termscheck.review.export import COLUMNS, rows_to_csv, safe_cell


@pytest.mark.parametrize("val", ['=HYPERLINK("http://x")', "+1+1", "-2+3", "@SUM(A1)", "\tx", "\rx"])
def test_formula_leading_text_is_neutralised(val):
    assert safe_cell("description", val) == "'" + val
    assert safe_cell("approval_comment", val) == "'" + val


def test_numbers_and_plain_text_untouched():
    assert safe_cell("unbooked_income_usd", "-38179.00") == "-38179.00"
    assert safe_cell("description", "Quarry GO 5%") == "Quarry GO 5%"
    assert safe_cell("description", None) == ""


def test_export_round_trip_is_safe():
    text = rows_to_csv([{"description": "=cmd|' /C calc'!A0", "unbooked_income_usd": "-5.00",
                         "finding_headline": "Unbooked income $5"}])
    row = next(csv.DictReader(io.StringIO(text)))
    assert row["description"].startswith("'=") and row["unbooked_income_usd"] == "-5.00"
    assert list(row) == COLUMNS


def test_unhandled_errors_do_not_leak_internals():
    from fastapi.testclient import TestClient

    from termscheck.api.app import create_app
    app = create_app()

    @app.get("/api/_boom")
    def boom():
        raise RuntimeError("postgresql://secret-user:secret-pass@db/termscheck")

    r = TestClient(app, raise_server_exceptions=False).get("/api/_boom")
    assert r.status_code == 500
    body = r.json()
    assert "secret" not in r.text and "RuntimeError" not in r.text
    assert body["error_id"] in body["detail"]


def test_compose_binds_localhost_only():
    from pathlib import Path
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text()
    ports = [l for l in compose.splitlines() if "ports:" in l]
    assert ports and all("127.0.0.1:" in l for l in ports)


# ---------------------------------------------------------------- upload / extraction robustness
def test_timeouts_fit_inside_the_proxy_timeout():
    import re
    from pathlib import Path

    from termscheck.settings import Settings
    s = Settings()
    nginx = (Path(__file__).resolve().parents[2] / "frontend" / "nginx.conf").read_text()
    proxy = int(re.search(r"proxy_read_timeout (\d+)s", nginx).group(1))
    assert (s.extraction_max_retries + 1) * s.extraction_timeout_s < proxy


def test_sdk_client_gets_explicit_timeout_and_retries(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    from termscheck.extraction.llm import AnthropicExtractionClient
    c = AnthropicExtractionClient(timeout=123.0, max_retries=1).client
    assert c.timeout == 123.0 and c.max_retries == 1


def test_scanned_pdf_detection():
    from termscheck.services.extraction import looks_scanned
    assert looks_scanned(["", " ", "12", ""])
    assert not looks_scanned(["x" * 500, "y" * 800, ""])


def test_unreadable_and_oversized_pdfs_are_rejected(monkeypatch):
    from termscheck.services.extraction import readable_pages
    from termscheck.settings import settings
    with pytest.raises(ValueError, match="could not be read"):
        readable_pages(b"%PDF-1.7 garbage")
    with pytest.raises(ValueError, match="must be a PDF"):
        readable_pages(b"hello")
    from pathlib import Path
    pdf = (Path(__file__).resolve().parents[2] / "data" / "sample_os" / "OS_FQ4TWLB23.pdf").read_bytes()
    monkeypatch.setattr(settings, "max_pdf_pages", 5)
    with pytest.raises(ValueError, match="limit is 5"):
        readable_pages(pdf)


@pytest.mark.db
def test_upload_size_limit_returns_413(client, monkeypatch):
    from termscheck.settings import settings
    monkeypatch.setattr(settings, "max_data_bytes", 1000)
    r = client.post("/api/uploads/holdings", files={"file": ("h.csv", "x" * 5000, "text/csv")})
    assert r.status_code == 413 and "upload limit" in r.json()["detail"]


@pytest.mark.db
def test_damaged_pdf_gives_422_and_stores_nothing(client, engine):
    from sqlalchemy import text
    r = client.post("/api/documents", data={"cusip": "FQ4TWLB23"},
                    files={"file": ("x.pdf", b"%PDF-1.7 not really", "application/pdf")})
    assert r.status_code == 422 and "could not be read" in r.json()["detail"]
    with engine.connect() as c:
        assert c.execute(text("select count(*) from document")).scalar() == 0


@pytest.mark.db
def test_scanned_pdf_marked_needs_ocr_without_model_call(client, screened, dataset):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    import io as _io
    buf = _io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for _ in range(3):
        c.rect(72, 72, 400, 600, fill=1)      # an "image" page with no text layer
        c.showPage()
    c.save()
    d01 = next(x for x in dataset.defects if x.defect_id.startswith("D01")).cusip
    r = client.post(f"/api/screen-runs/{screened['run']}/cusips/{d01}/official-statement",
                    files={"file": ("scan.pdf", buf.getvalue(), "application/pdf")}).json()
    assert r["extraction"]["status"] == "needs_ocr" and "OCR" in r["error"] and r["finding"] is None
    ev = client.get("/api/audit?event_type=extraction.needs_ocr").json()
    assert len(ev) == 1


# ---------------------------------------------------------------- unsupported cases and callables
def test_unsupported_products_are_refused():
    from dataclasses import replace

    from termscheck.core.plugin import get_plugin
    from termscheck.plugins.agency_mbs.synthetic import generate
    mbs = get_plugin("agency_mbs")
    rec = generate().holdings[0].book
    assert mbs.unsupported_reason(rec, {"product_type": "pass_through"}) is None
    for p in ("cmo", "io", "po"):
        assert "not implemented" in mbs.unsupported_reason(replace(rec, product_type=p), {})
    assert "offering document says io" in mbs.unsupported_reason(rec, {"product_type": "io"})
    from termscheck.plugins.muni.synthetic import generate as gen_muni
    muni = get_plugin("muni")
    m = gen_muni().holdings[0].vendor_a
    assert muni.unsupported_reason(m, None) is None
    assert "floating-rate" in muni.unsupported_reason(replace(m, accrual_type="floating"), None)


def test_mbs_tool_refuses_unsupported_products():
    from termscheck.tools import compute_mbs_treatment
    with pytest.raises(ValueError, match="unsupported product"):
        compute_mbs_treatment({}, {"cusip": "X"}, 1.0, "2026-11-30", [], product_type="cmo")


def test_premium_callable_quoted_to_call_not_flagged():
    from datetime import date

    from termscheck.core.records import Position, ScreenInput, SecurityRecord
    from termscheck.screens import run_screens
    rec = SecurityRecord(vendor="A", cusip="TEST00001", description="callable", price=110.0, price_convention="clean",
                         coupon=0.05, accrual_type="fixed", maturity_date=date(2046, 6, 1), issue_date=date(2016, 6, 1),
                         rating="AA", sector="General Obligation", state="NY", payment_frequency=2, day_count="30/360",
                         vendor_yield=0.025)    # yield to a 2029 call; YTM at 110 is ~4.2%
    data = ScreenInput(date(2026, 11, 30), [Position("P", rec.cusip, 1e6)], {rec.cusip: rec})
    assert not [f for f in run_screens(data).flags if f.rule == "yield_coupon_impossibility"]
    from dataclasses import replace
    high = replace(rec, vendor_yield=0.09)        # above the YTM: still a real inconsistency
    data = ScreenInput(date(2026, 11, 30), [Position("P", rec.cusip, 1e6)], {rec.cusip: high})
    assert [f for f in run_screens(data).flags if f.rule == "yield_coupon_impossibility"]
