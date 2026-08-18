"""athlete preferences

Weekly session pattern: which days the athlete runs, which sessions are fixed
commitments (a club threshold night, a Sunday social run) and which the engine
is free to size. Stored per athlete because it is a constraint on their life,
not a training-theory decision.

Revision ID: 0003
Revises: 0002
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("athlete", sa.Column("preferences", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("athlete", "preferences")
