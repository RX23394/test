"""Add persistent ownership tokens for document indexing jobs.

Revision ID: 20260806_0007
Revises: 20260716_0006
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260806_0007"
down_revision: str | Sequence[str] | None = "20260716_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Store the UUID of the active document indexing job."""
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(sa.Column("indexing_job_id", sa.String(length=36)))


def downgrade() -> None:
    """Remove the document indexing ownership token."""
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_column("indexing_job_id")
