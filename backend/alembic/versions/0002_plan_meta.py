"""plan metadata

Stores the derivation alongside the plan — pace table, warnings, peak targets —
so a plan generated months ago can still be explained without re-running the
engine against fitness that has since moved.

Revision ID: 0002
Revises: 0001
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("plan", sa.Column("meta", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("plan", "meta")
