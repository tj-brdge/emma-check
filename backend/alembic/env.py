from alembic import context
from sqlalchemy import create_engine

from termscheck.db import models  # noqa: F401  (register tables)
from termscheck.db.base import Base
from termscheck.settings import settings

target_metadata = Base.metadata


def url() -> str:
    return context.config.attributes.get("url") or settings.migration_database_url or settings.database_url


def run_migrations_offline() -> None:
    context.configure(url=url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    conn = context.config.attributes.get("connection")
    if conn is not None:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
