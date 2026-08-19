"""per-kilometre splits

Strava returns `laps` and `splits_metric` on the activity detail. Laps are
useless for this athlete — the lap button is never pressed, so every run has
exactly one — but `splits_metric` gives a clean per-kilometre breakdown, which
is what a pace chart and a fade analysis actually need.

Revision ID: 0004
Revises: 0003
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activity_split",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "activity_id",
            sa.Integer(),
            sa.ForeignKey("activity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("split_index", sa.Integer(), nullable=False),
        sa.Column("distance_m", sa.Float(), nullable=False),
        sa.Column("elapsed_time_s", sa.Integer(), nullable=False),
        sa.Column("moving_time_s", sa.Integer(), nullable=False),
        sa.Column("elevation_diff_m", sa.Float()),
        sa.Column("avg_speed", sa.Float()),
        sa.Column("avg_hr", sa.Float()),
        sa.UniqueConstraint("activity_id", "split_index", name="uq_split_activity_index"),
    )
    op.create_index("ix_activity_split_activity_id", "activity_split", ["activity_id"])


def downgrade() -> None:
    op.drop_table("activity_split")
