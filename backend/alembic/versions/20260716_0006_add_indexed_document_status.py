"""Add indexed to the document status constraint.

Revision ID: 20260716_0006
Revises: 20260716_0005
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260716_0006"
down_revision: str | Sequence[str] | None = "20260716_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_STATUSES = ("pending", "processing", "completed", "failed")
NEW_STATUSES = (*OLD_STATUSES, "indexed")


def _status_enum(values: tuple[str, ...]) -> sa.Enum:
    """Build the non-native document status enum used by SQLite."""
    return sa.Enum(
        *values,
        name="document_status",
        native_enum=False,
        create_constraint=True,
    )


def upgrade() -> None:
    """Allow documents to transition to the indexed state."""
    with op.batch_alter_table("documents", recreate="always") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=_status_enum(OLD_STATUSES),
            type_=_status_enum(NEW_STATUSES),
            existing_nullable=False,
            existing_server_default="pending",
        )


def downgrade() -> None:
    """Remove indexed from the document status constraint."""
    op.execute("UPDATE documents SET status = 'completed' WHERE status = 'indexed'")
    with op.batch_alter_table("documents", recreate="always") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=_status_enum(NEW_STATUSES),
            type_=_status_enum(OLD_STATUSES),
            existing_nullable=False,
            existing_server_default="pending",
        )
