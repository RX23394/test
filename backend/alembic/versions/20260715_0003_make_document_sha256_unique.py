"""Make document SHA-256 digests unique.

Revision ID: 20260715_0003
Revises: 20260715_0002
Create Date: 2026-07-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260715_0003"
down_revision: str | Sequence[str] | None = "20260715_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Replace the document digest index with a unique index."""
    op.drop_index(op.f("ix_documents_sha256"), table_name="documents")
    op.create_index(
        op.f("ix_documents_sha256"),
        "documents",
        ["sha256"],
        unique=True,
    )


def downgrade() -> None:
    """Restore the non-unique document digest index."""
    op.drop_index(op.f("ix_documents_sha256"), table_name="documents")
    op.create_index(
        op.f("ix_documents_sha256"),
        "documents",
        ["sha256"],
        unique=False,
    )
