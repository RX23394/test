"""Create the standalone chunk_index FTS5 table.

Revision ID: 20260716_0005
Revises: 20260715_0004
Create Date: 2026-07-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260716_0005"
down_revision: str | Sequence[str] | None = "20260715_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the FTS5 chunk index for standalone full-text search."""
    op.execute(
        """
        CREATE VIRTUAL TABLE chunk_index USING fts5(
            chunk_id UNINDEXED,
            document_id UNINDEXED,
            content,
            tokenize='unicode61'
        )
        """
    )


def downgrade() -> None:
    """Drop the standalone FTS5 chunk index."""
    op.execute("DROP TABLE chunk_index")
