import pytest

from termscheck.screens import run_screens
from termscheck.synthetic import generate, to_screen_input


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
        pytest.skip(f"PostgreSQL not available for db tests: {e}")
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
            c.execute(text("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE"))
    S = sessionmaker(engine, expire_on_commit=False)
    with S() as s:
        yield s


@pytest.fixture
def client(engine, db):
    from fastapi.testclient import TestClient

    from termscheck.api.app import create_app
    from termscheck.db.session import get_session

    app = create_app()
    S = sessionmaker(engine, expire_on_commit=False)

    def _session():
        with S() as s:
            yield s

    app.dependency_overrides[get_session] = _session
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
