"""Add pending_delete to the document status constraint.

Revision ID: 20261010_0009
Revises: 20260930_0008
Create Date: 2026-10-10

Deletion has to mark the row before it touches Qdrant, FTS5, and the source
file, so that a crash in the middle leaves a visible ``pending_delete`` document
instead of orphaned vectors. The status constraint therefore needs the extra
value.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261010_0009"
down_revision: str | Sequence[str] | None = "20260930_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_STATUSES = ("pending", "processing", "completed", "failed", "indexed")
NEW_STATUSES = (*OLD_STATUSES, "pending_delete")


def _status_enum(values: tuple[str, ...]) -> sa.Enum:
    """Build the non-native document status enum used by SQLite."""
    return sa.Enum(
        *values,
        name="document_status",
        native_enum=False,
        create_constraint=True,
    )


def upgrade() -> None:
    """Allow documents to be marked for deletion before their indexes are gone."""
    with op.batch_alter_table("documents", recreate="always") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=_status_enum(OLD_STATUSES),
            type_=_status_enum(NEW_STATUSES),
            existing_nullable=False,
            existing_server_default="pending",
        )


def downgrade() -> None:
    """Remove pending_delete, surfacing abandoned deletions as failures."""
    op.execute("UPDATE documents SET status = 'failed' WHERE status = 'pending_delete'")
    with op.batch_alter_table("documents", recreate="always") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=_status_enum(NEW_STATUSES),
            type_=_status_enum(OLD_STATUSES),
            existing_nullable=False,
            existing_server_default="pending",
        )
