"""least-privilege grants for the application role (if it exists)

The API connects as termscheck_app: it may read everything, insert into every table, and
update only finding.status. No UPDATE/DELETE/TRUNCATE anywhere else, independent of the
append-only triggers. Skipped when the role does not exist (e.g. local dev / tests).

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

GRANTS = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'termscheck_app') THEN
    GRANT USAGE ON SCHEMA public TO termscheck_app;
    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM termscheck_app;
    GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO termscheck_app;
    GRANT UPDATE (status) ON finding TO termscheck_app;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO termscheck_app;
  END IF;
END $$;
"""


def upgrade() -> None:
    op.execute(GRANTS)


def downgrade() -> None:
    op.execute("""
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'termscheck_app') THEN
    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM termscheck_app;
  END IF;
END $$;""")
