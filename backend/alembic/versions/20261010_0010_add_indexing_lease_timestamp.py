"""Add the indexing lease timestamp.

Revision ID: 20261010_0010
Revises: 20261010_0009
Create Date: 2026-10-10

``indexing_job_id`` records who owns an indexing task but not since when, so a
worker that crashed mid-index left the document in ``processing`` with no retry
path. The lease timestamp makes the stuck state detectable.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261010_0010"
down_revision: str | Sequence[str] | None = "20261010_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Store the start time of the active indexing lease."""
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(
            sa.Column("indexing_started_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    """Remove the indexing lease timestamp."""
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_column("indexing_started_at")
