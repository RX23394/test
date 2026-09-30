"""Create document chunks FTS5 table.

Revision ID: 20260715_0004
Revises: 20260715_0003
Create Date: 2026-07-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260715_0004"
down_revision: str | Sequence[str] | None = "20260715_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the FTS5 virtual table used for lexical retrieval."""
    op.execute(
        """
        CREATE VIRTUAL TABLE document_chunks_fts USING fts5(
            document_id UNINDEXED,
            chunk_index UNINDEXED,
            content,
            page UNINDEXED,
            section UNINDEXED,
            tokenize='unicode61'
        )
        """
    )


def downgrade() -> None:
    """Drop the document chunks FTS5 virtual table."""
    op.execute("DROP TABLE document_chunks_fts")
