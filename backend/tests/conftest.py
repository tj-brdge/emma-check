import pytest

from termscheck.screens import run_screens
from termscheck.plugins.muni.synthetic import generate, to_screen_input


@pytest.fixture(scope="session")
def dataset():
    return generate()


@pytest.fixture(scope="session")
def screen_result(dataset):
    return run_screens(to_screen_input(dataset))


# ---------------------------------------------------------------- database fixtures
import os  # noqa: E402

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

TEST_DB = os.environ.get("TERMSCHECK_TEST_DATABASE_URL",
                         "postgresql+psycopg://termscheck:termscheck@localhost:5432/termscheck_test")


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DB, future=True)
    try:
        with eng.connect() as c:
            c.execute(text("select 1"))
    except Exception as e:  # pragma: no cover
        if os.environ.get("TERMSCHECK_ALLOW_NO_DB") == "1":
            pytest.skip(f"PostgreSQL not available for db tests: {e}")
        pytest.fail(f"PostgreSQL not reachable at {TEST_DB} (set TERMSCHECK_ALLOW_NO_DB=1 to skip db tests): {e}")
    from alembic import command
    from alembic.config import Config
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    with eng.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    return eng


@pytest.fixture
def db(engine):
    with engine.begin() as c:
        tables = [r[0] for r in c.execute(text(
            "select tablename from pg_tables where schemaname='public' and tablename<>'alembic_version'"))]
        if tables:
            # Append-only triggers block TRUNCATE; tests (superuser) bypass them via replica mode.
            c.execute(text("SET LOCAL session_replication_role = replica"))
            c.execute(text("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE"))
    S = sessionmaker(engine, expire_on_commit=False)
    with S() as s:
        yield s


@pytest.fixture
def client(engine, db, tmp_path_factory, recorded_llm):
    from fastapi.testclient import TestClient

    from termscheck.api.app import create_app
    from termscheck.db.session import get_session

    app = create_app()
    S = sessionmaker(engine, expire_on_commit=False)

    def _session():
        with S() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    from termscheck.api.deps import get_llm, get_store
    from termscheck.extraction.sources import UploadSource
    store = UploadSource(tmp_path_factory.mktemp("store"))
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_llm] = lambda: recorded_llm
    c = TestClient(app)
    c.headers["X-User"] = "test.reviewer"
    return c


@pytest.fixture(scope="session")
def synthetic_csvs(dataset):
    from termscheck.ingest import history_csv, holdings_csv, vendor_csv
    return {
        "holdings": holdings_csv([(h.position, h.vendor_a) for h in dataset.holdings]),
        "vendor_secondary": vendor_csv([h.vendor_b for h in dataset.holdings if h.vendor_b]),
        "price_history": history_csv([p for h in dataset.holdings for p in h.history]),
    }


@pytest.fixture(scope="session")
def recorded_llm():
    """Serves tests/fixtures/recorded_extraction_<defect>.json by target CUSIP."""
    import json
    import re
    from pathlib import Path

    from termscheck.extraction.llm import ExtractionLLMError, RecordedExtractionClient
    ds = generate()
    by_cusip = {}
    for d in ds.defects:
        f = Path(__file__).parent / "fixtures" / f"recorded_extraction_{d.defect_id[:3]}.json"
        if f.exists():
            by_cusip[d.cusip] = json.loads(f.read_text())

    class _LLM:
        def extract(self, *, system, user, model, max_tokens, schema):
            c = re.search(r"Target CUSIP: (\w{9})", user).group(1)
            if c not in by_cusip:
                raise ExtractionLLMError("no recording")
            return RecordedExtractionClient(by_cusip[c], model="recorded").extract(
                system=system, user=user, model=model, max_tokens=max_tokens, schema=schema)

    return _LLM()


@pytest.fixture
def screened(client, synthetic_csvs, dataset):
    """Upload the synthetic files and run screens; returns ids."""
    ids = {}
    for kind in ("holdings", "vendor_secondary", "price_history"):
        r = client.post(f"/api/uploads/{kind}", files={"file": (f"{kind}.csv", synthetic_csvs[kind], "text/csv")})
        ids[kind] = r.json()["batch"]["id"]
    run = client.post("/api/screen-runs", json={
        "as_of": dataset.as_of.isoformat(), "holdings_batch_id": ids["holdings"],
        "secondary_batch_id": ids["vendor_secondary"], "history_batch_id": ids["price_history"]}).json()
    ids["run"] = run["id"]
    return ids
