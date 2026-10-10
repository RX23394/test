"""Database schema statements shared by migrations and application startup.

Only statements that represent the schema the current application code queries
belong here. Historical revisions under ``alembic/versions`` keep their own
frozen copies and must never be rewritten to import from this module: a
migration has to keep describing the schema as it was at that revision.
"""

from collections.abc import Sequence

DOCUMENT_CHUNKS_FTS_TABLE = "document_chunks_fts"

# Logical columns per table, in FTS5 declaration order, paired with whether the
# column is stored but not full-text indexed.
DOCUMENT_CHUNKS_FTS_COLUMNS: tuple[tuple[str, bool], ...] = (
    ("document_id", True),
    ("chunk_index", True),
    ("content", True),
    ("page", True),
    ("section", True),
    # Chinese text cannot be searched through unicode61 alone, so the jieba
    # token stream is indexed here and ``content`` is only stored. See
    # ``app/services/tokenization.py``.
    ("content_tokens", False),
)

# SQLite only enforces ``ON DELETE CASCADE`` when foreign key enforcement is
# enabled per connection; it is off by default. Models rely on it through
# ``passive_deletes=True``, so the pragma is part of the correctness contract.
SQLITE_FOREIGN_KEYS_PRAGMA = "PRAGMA foreign_keys=ON"


def build_fts5_ddl(
    table: str,
    columns: Sequence[tuple[str, bool]],
    tokenize: str,
) -> str:
    """Build an FTS5 ``CREATE VIRTUAL TABLE`` statement for the given columns."""
    declarations = ",\n            ".join(
        f"{name} UNINDEXED" if unindexed else name for name, unindexed in columns
    )
    return (
        f"CREATE VIRTUAL TABLE {table} USING fts5(\n"
        f"            {declarations},\n"
        f"            tokenize='{tokenize}'\n"
        f"        )"
    )


def current_document_chunks_fts_ddl() -> str:
    """Return the search-index DDL the current application code queries."""
    return build_fts5_ddl(
        DOCUMENT_CHUNKS_FTS_TABLE,
        DOCUMENT_CHUNKS_FTS_COLUMNS,
        "unicode61",
    )
