"""Move the keyword index to an external-content FTS5 table.

Revision ID: 20261010_0012
Revises: 20261010_0011
Create Date: 2026-10-10

The previous index stored chunk text and metadata inside the FTS5 virtual table
with every column marked UNINDEXED, so any lookup that was not a MATCH -- for
example deleting one document's chunks -- scanned the whole virtual table. The
chunks now live in the ordinary ``document_chunk_rows`` table (indexed by
``document_id``) and FTS5 keeps only the token stream, synchronised by triggers.

Migration steps: read the existing rows out of the old virtual table, replace it
with the content table plus the external-content index and its triggers, then
re-insert the rows so the triggers tokenize them.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261010_0012"
down_revision: str | Sequence[str] | None = "20261010_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_FTS_TABLE = "document_chunks_fts"
CHUNK_ROWS_TABLE = "document_chunk_rows"
CHUNK_ROWS_INDEX = "ix_document_chunk_rows_document_id"
FTS_INDEXED_COLUMN = "content_tokens"


def _create_content_table() -> None:
    """Create the table that now owns chunk text and metadata."""
    op.execute(
        f"""
        CREATE TABLE {CHUNK_ROWS_TABLE} (
            id INTEGER PRIMARY KEY,
            document_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            page INTEGER,
            section TEXT,
            {FTS_INDEXED_COLUMN} TEXT NOT NULL,
            FOREIGN KEY (document_id) REFERENCES documents (id)
                ON DELETE CASCADE
        )
        """
    )
    op.execute(
        f"CREATE INDEX {CHUNK_ROWS_INDEX} " f"ON {CHUNK_ROWS_TABLE} (document_id)"
    )


def _create_fts_table() -> None:
    """Create the external-content search index."""
    op.execute(
        f"""
        CREATE VIRTUAL TABLE {OLD_FTS_TABLE} USING fts5(
            {FTS_INDEXED_COLUMN},
            content='{CHUNK_ROWS_TABLE}',
            content_rowid='id',
            tokenize='unicode61'
        )
        """
    )


def _create_triggers() -> None:
    """Keep the index in step with the content table."""
    op.execute(
        f"""
        CREATE TRIGGER {CHUNK_ROWS_TABLE}_ai
        AFTER INSERT ON {CHUNK_ROWS_TABLE} BEGIN
            INSERT INTO {OLD_FTS_TABLE}(rowid, {FTS_INDEXED_COLUMN})
            VALUES (new.id, new.{FTS_INDEXED_COLUMN});
        END
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {CHUNK_ROWS_TABLE}_ad
        AFTER DELETE ON {CHUNK_ROWS_TABLE} BEGIN
            INSERT INTO {OLD_FTS_TABLE}(
                {OLD_FTS_TABLE}, rowid, {FTS_INDEXED_COLUMN}
            )
            VALUES ('delete', old.id, old.{FTS_INDEXED_COLUMN});
        END
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {CHUNK_ROWS_TABLE}_au
        AFTER UPDATE ON {CHUNK_ROWS_TABLE} BEGIN
            INSERT INTO {OLD_FTS_TABLE}(
                {OLD_FTS_TABLE}, rowid, {FTS_INDEXED_COLUMN}
            )
            VALUES ('delete', old.id, old.{FTS_INDEXED_COLUMN});
            INSERT INTO {OLD_FTS_TABLE}(rowid, {FTS_INDEXED_COLUMN})
            VALUES (new.id, new.{FTS_INDEXED_COLUMN});
        END
        """
    )


def upgrade() -> None:
    """Rebuild the keyword index as an external-content table."""
    connection = op.get_bind()
    existing_rows = [
        dict(row)
        for row in connection.execute(
            sa.text(
                f"""
                SELECT document_id, chunk_index, content, page, section,
                       {FTS_INDEXED_COLUMN}
                FROM {OLD_FTS_TABLE}
                """
            )
        ).mappings()
    ]

    op.execute(f"DROP TABLE {OLD_FTS_TABLE}")
    _create_content_table()
    _create_fts_table()
    _create_triggers()

    if existing_rows:
        connection.execute(
            sa.text(
                f"""
                INSERT INTO {CHUNK_ROWS_TABLE}
                    (document_id, chunk_index, content, page, section,
                     {FTS_INDEXED_COLUMN})
                VALUES
                    (:document_id, :chunk_index, :content, :page, :section,
                     :{FTS_INDEXED_COLUMN})
                """
            ),
            existing_rows,
        )


def downgrade() -> None:
    """Restore the self-contained FTS5 table that stored its own content."""
    connection = op.get_bind()
    existing_rows = [
        dict(row)
        for row in connection.execute(
            sa.text(
                f"""
                SELECT document_id, chunk_index, content, page, section,
                       {FTS_INDEXED_COLUMN}
                FROM {CHUNK_ROWS_TABLE}
                """
            )
        ).mappings()
    ]

    op.execute(f"DROP TRIGGER {CHUNK_ROWS_TABLE}_ai")
    op.execute(f"DROP TRIGGER {CHUNK_ROWS_TABLE}_ad")
    op.execute(f"DROP TRIGGER {CHUNK_ROWS_TABLE}_au")
    op.execute(f"DROP TABLE {OLD_FTS_TABLE}")
    op.execute(f"DROP INDEX {CHUNK_ROWS_INDEX}")
    op.execute(f"DROP TABLE {CHUNK_ROWS_TABLE}")
    op.execute(
        f"""
        CREATE VIRTUAL TABLE {OLD_FTS_TABLE} USING fts5(
            document_id UNINDEXED,
            chunk_index UNINDEXED,
            content UNINDEXED,
            page UNINDEXED,
            section UNINDEXED,
            {FTS_INDEXED_COLUMN},
            tokenize='unicode61'
        )
        """
    )

    if existing_rows:
        connection.execute(
            sa.text(
                f"""
                INSERT INTO {OLD_FTS_TABLE}
                    (document_id, chunk_index, content, page, section,
                     {FTS_INDEXED_COLUMN})
                VALUES
                    (:document_id, :chunk_index, :content, :page, :section,
                     :{FTS_INDEXED_COLUMN})
                """
            ),
            existing_rows,
        )
