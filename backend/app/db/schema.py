"""Database schema statements shared by migrations and application startup.

Only statements that represent the schema the current application code queries
belong here. Historical revisions under ``alembic/versions`` keep their own
frozen copies and must never be rewritten to import from this module: a
migration has to keep describing the schema as it was at that revision.

The keyword index is an FTS5 **external-content** table: ``document_chunks_fts``
stores only the token stream and reads its content from
``document_chunk_rows``. That keeps the chunk metadata in an ordinary table --
so ``document_id`` lookups (replacing or deleting a document's chunks) use a
real index instead of scanning the virtual table -- and the triggers below keep
the search index in step with it.
"""

# Chunk text lives here; the FTS5 index only references these rows by rowid.
DOCUMENT_CHUNK_ROWS_TABLE = "document_chunk_rows"
DOCUMENT_CHUNKS_FTS_TABLE = "document_chunks_fts"
DOCUMENT_CHUNK_ROWS_INDEX = "ix_document_chunk_rows_document_id"

# Logical columns of the content table in declaration order.
DOCUMENT_CHUNK_ROW_COLUMNS: tuple[str, ...] = (
    "document_id",
    "chunk_index",
    "content",
    "page",
    "section",
    # Chinese text cannot be searched through unicode61 alone, so the jieba
    # token stream is indexed here and ``content`` is only stored. See
    # ``app/services/tokenization.py``.
    "content_tokens",
)

# The single column the FTS5 index tokenizes.
FTS_INDEXED_COLUMN = "content_tokens"

# SQLite only enforces ``ON DELETE CASCADE`` when foreign key enforcement is
# enabled per connection; it is off by default. Models rely on it through
# ``passive_deletes=True``, so the pragma is part of the correctness contract.
SQLITE_FOREIGN_KEYS_PRAGMA = "PRAGMA foreign_keys=ON"


def current_document_chunk_rows_ddl() -> str:
    """Return the content-table DDL the keyword index reads through."""
    columns = ",\n            ".join(
        f"{name} TEXT" if name in ("content", "content_tokens") else f"{name} INTEGER"
        for name in DOCUMENT_CHUNK_ROW_COLUMNS
    )
    return (
        f"CREATE TABLE {DOCUMENT_CHUNK_ROWS_TABLE} (\n"
        "            id INTEGER PRIMARY KEY,\n"
        f"            {columns},\n"
        "            FOREIGN KEY (document_id) REFERENCES documents (id)\n"
        "                ON DELETE CASCADE\n"
        "        )"
    )


def current_document_chunk_rows_index_ddl() -> str:
    """Return the index that keeps document-scoped chunk lookups cheap."""
    return (
        f"CREATE INDEX {DOCUMENT_CHUNK_ROWS_INDEX} "
        f"ON {DOCUMENT_CHUNK_ROWS_TABLE} (document_id)"
    )


def current_document_chunks_fts_ddl() -> str:
    """Return the external-content FTS5 DDL the application queries."""
    return (
        f"CREATE VIRTUAL TABLE {DOCUMENT_CHUNKS_FTS_TABLE} USING fts5(\n"
        f"            {FTS_INDEXED_COLUMN},\n"
        f"            content='{DOCUMENT_CHUNK_ROWS_TABLE}',\n"
        "            content_rowid='id',\n"
        "            tokenize='unicode61'\n"
        "        )"
    )


def current_document_chunks_fts_trigger_ddl() -> list[str]:
    """Return the triggers that mirror content-table writes into the index."""
    return [
        (
            f"CREATE TRIGGER {DOCUMENT_CHUNK_ROWS_TABLE}_ai "
            f"AFTER INSERT ON {DOCUMENT_CHUNK_ROWS_TABLE} BEGIN\n"
            f"    INSERT INTO {DOCUMENT_CHUNKS_FTS_TABLE}"
            f"(rowid, {FTS_INDEXED_COLUMN})\n"
            f"    VALUES (new.id, new.{FTS_INDEXED_COLUMN});\n"
            "END"
        ),
        (
            f"CREATE TRIGGER {DOCUMENT_CHUNK_ROWS_TABLE}_ad "
            f"AFTER DELETE ON {DOCUMENT_CHUNK_ROWS_TABLE} BEGIN\n"
            f"    INSERT INTO {DOCUMENT_CHUNKS_FTS_TABLE}"
            f"({DOCUMENT_CHUNKS_FTS_TABLE}, rowid, {FTS_INDEXED_COLUMN})\n"
            f"    VALUES ('delete', old.id, old.{FTS_INDEXED_COLUMN});\n"
            "END"
        ),
        (
            f"CREATE TRIGGER {DOCUMENT_CHUNK_ROWS_TABLE}_au "
            f"AFTER UPDATE ON {DOCUMENT_CHUNK_ROWS_TABLE} BEGIN\n"
            f"    INSERT INTO {DOCUMENT_CHUNKS_FTS_TABLE}"
            f"({DOCUMENT_CHUNKS_FTS_TABLE}, rowid, {FTS_INDEXED_COLUMN})\n"
            f"    VALUES ('delete', old.id, old.{FTS_INDEXED_COLUMN});\n"
            f"    INSERT INTO {DOCUMENT_CHUNKS_FTS_TABLE}"
            f"(rowid, {FTS_INDEXED_COLUMN})\n"
            f"    VALUES (new.id, new.{FTS_INDEXED_COLUMN});\n"
            "END"
        ),
    ]


def current_search_index_ddl() -> list[str]:
    """Return every statement that creates the current keyword index."""
    return [
        current_document_chunk_rows_ddl(),
        current_document_chunk_rows_index_ddl(),
        current_document_chunks_fts_ddl(),
        *current_document_chunks_fts_trigger_ddl(),
    ]


def drop_search_index_ddl() -> list[str]:
    """Return every statement that removes the current keyword index.

    Test fixtures use this before dropping the ORM tables: the content table
    references ``documents``, and SQLite refuses to drop a referenced table while
    its cascade would still fire the index triggers.
    """
    return [
        f"DROP TRIGGER IF EXISTS {DOCUMENT_CHUNK_ROWS_TABLE}_ai",
        f"DROP TRIGGER IF EXISTS {DOCUMENT_CHUNK_ROWS_TABLE}_ad",
        f"DROP TRIGGER IF EXISTS {DOCUMENT_CHUNK_ROWS_TABLE}_au",
        f"DROP TABLE IF EXISTS {DOCUMENT_CHUNKS_FTS_TABLE}",
        f"DROP INDEX IF EXISTS {DOCUMENT_CHUNK_ROWS_INDEX}",
        f"DROP TABLE IF EXISTS {DOCUMENT_CHUNK_ROWS_TABLE}",
    ]
