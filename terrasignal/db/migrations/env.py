"""Alembic environment. Migrations are hand-written; no autogenerate target."""

import os

from alembic import context
from sqlalchemy import create_engine

DEFAULT_URL = "postgresql+psycopg://terrasignal:terrasignal_local_dev@localhost:5433/terrasignal"


def _url() -> str:
    return os.environ.get("TERRASIGNAL_DATABASE_URL_SYNC", DEFAULT_URL)


def run_migrations_offline() -> None:
    context.configure(url=_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url())
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
