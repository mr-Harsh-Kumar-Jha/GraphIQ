"""Alembic env.py — reads POSTGRES_URL from .env and runs sync migrations."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from dotenv import load_dotenv

# Load .env so POSTGRES_URL etc. are available
load_dotenv()

config = context.config

# Configure logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import your metadata here
# from app.db import Base
# target_metadata = Base.metadata
target_metadata = None  # TODO: set to your Base.metadata

postgres_url = os.environ.get("POSTGRES_URL")
if not postgres_url:
    raise RuntimeError("POSTGRES_URL is not set")

# If elsewhere you use asyncpg-style URLs, adapt here; otherwise this is fine
sync_url = postgres_url.replace("postgresql://", "postgresql+psycopg2://")


def run_migrations_offline() -> None:
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(sync_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()