"""Add the per-user token version.

Revision ID: 20261010_0011
Revises: 20261010_0010
Create Date: 2026-10-10

Logout only cleared the cookie, so a copied access token stayed valid for its
full lifetime. The version column lets the API revoke every outstanding token of
a user; existing rows start at 1, which is also the default assumed for tokens
issued before this revision.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261010_0011"
down_revision: str | Sequence[str] | None = "20261010_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the token generation counter to users."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "token_version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )


def downgrade() -> None:
    """Remove the token generation counter."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("token_version")
