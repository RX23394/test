"""Alembic migration environment."""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from app.models import Conversation, Document, Message, User  # noqa: F401

config = context.config

if config.config_file_name is not None:
    # Keep application loggers alive: migrations also run inside the application
    # process (for example from the database contract test), and the default
    # disable_existing_loggers=True would silence every logger created so far.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata
# The search tables are FTS5 virtual tables. SQLAlchemy cannot represent them in
# metadata, so they stay owned by the migrations that create them and are
# excluded from autogenerate instead of being recreated as plain tables.
FTS_TABLE_PREFIXES = ("document_chunks_fts", "chunk_index")


def include_object(
    object_: object,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: object | None,
) -> bool:
    """Exclude migration-managed FTS5 virtual and shadow tables from autogenerate."""
    del object_, type_, compare_to
    return not (
        reflected
        and name is not None
        and any(
            name == prefix or name.startswith(f"{prefix}_")
            for prefix in FTS_TABLE_PREFIXES
        )
    )


def run_migrations_offline() -> None:
    """Run migrations without creating an engine."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        # SQLite cannot ALTER most columns in place, so autogenerate has to emit
        # batch operations; without this the next ALTER raises on SQLite.
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a SQLAlchemy connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
