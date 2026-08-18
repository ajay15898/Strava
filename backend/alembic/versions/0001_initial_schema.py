"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "athlete",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("strava_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=200)),
        sa.Column("max_hr", sa.Integer()),
        sa.Column("ftp", sa.Integer()),
        sa.Column("measurement_pref", sa.String(length=16), server_default="metric"),
        sa.Column("goal_race_distance_m", sa.Float()),
        sa.Column("goal_time_s", sa.Integer()),
        sa.Column("goal_race_date", sa.Date()),
        sa.Column("max_sessions_per_week", sa.Integer()),
        sa.UniqueConstraint("strava_id"),
    )
    op.create_index("ix_athlete_strava_id", "athlete", ["strava_id"])

    op.create_table(
        "oauth_token",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "athlete_id",
            sa.Integer(),
            sa.ForeignKey("athlete.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("access_token", sa.String(length=255), nullable=False),
        sa.Column("refresh_token", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", sa.String(length=255)),
        sa.UniqueConstraint("athlete_id"),
    )
    op.create_index("ix_oauth_token_athlete_id", "oauth_token", ["athlete_id"])

    op.create_table(
        "activity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("strava_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "athlete_id",
            sa.Integer(),
            sa.ForeignKey("athlete.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sport_type", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=255)),
        sa.Column("start_local", sa.DateTime(), nullable=False),
        sa.Column("start_utc", sa.DateTime(timezone=True)),
        sa.Column("distance_m", sa.Float(), server_default="0"),
        sa.Column("moving_time_s", sa.Integer(), server_default="0"),
        sa.Column("elapsed_time_s", sa.Integer(), server_default="0"),
        sa.Column("elevation_gain_m", sa.Float()),
        sa.Column("avg_speed", sa.Float()),
        sa.Column("max_speed", sa.Float()),
        sa.Column("avg_hr", sa.Float()),
        sa.Column("max_hr", sa.Float()),
        sa.Column("has_heartrate", sa.Boolean(), server_default=sa.false()),
        sa.Column("avg_watts", sa.Float()),
        sa.Column("has_device_watts", sa.Boolean(), server_default=sa.false()),
        sa.Column("avg_cadence", sa.Float()),
        sa.Column("calories", sa.Float()),
        sa.Column("relative_effort", sa.Float()),
        sa.Column("pr_count", sa.Integer()),
        sa.Column("achievement_count", sa.Integer()),
        sa.Column("gear_id", sa.String(length=64)),
        sa.Column("polyline", sa.Text()),
        sa.Column("is_duplicate", sa.Boolean(), server_default=sa.false()),
        sa.Column("duplicate_of_strava_id", sa.BigInteger()),
        sa.Column("streams_fetched", sa.Boolean(), server_default=sa.false()),
        sa.UniqueConstraint("strava_id"),
    )
    op.create_index("ix_activity_strava_id", "activity", ["strava_id"])
    op.create_index("ix_activity_athlete_id", "activity", ["athlete_id"])
    op.create_index("ix_activity_sport_type", "activity", ["sport_type"])
    op.create_index("ix_activity_start_local", "activity", ["start_local"])
    op.create_index("ix_activity_is_duplicate", "activity", ["is_duplicate"])
    op.create_index("ix_activity_athlete_start", "activity", ["athlete_id", "start_local"])

    op.create_table(
        "activity_stream",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "activity_id",
            sa.Integer(),
            sa.ForeignKey("activity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("activity_id", "type", name="uq_stream_activity_type"),
    )
    op.create_index("ix_activity_stream_activity_id", "activity_stream", ["activity_id"])

    op.create_table(
        "best_effort",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "activity_id",
            sa.Integer(),
            sa.ForeignKey("activity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("strava_effort_id", sa.BigInteger()),
        sa.Column("effort_type", sa.String(length=40), nullable=False),
        sa.Column("duration_s", sa.Integer(), nullable=False),
        sa.Column("distance_m", sa.Float(), nullable=False),
        sa.UniqueConstraint("activity_id", "effort_type", name="uq_effort_activity_type"),
    )
    op.create_index("ix_best_effort_activity_id", "best_effort", ["activity_id"])
    op.create_index("ix_best_effort_effort_type", "best_effort", ["effort_type"])

    op.create_table(
        "daily_load",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "athlete_id",
            sa.Integer(),
            sa.ForeignKey("athlete.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("load", sa.Float(), server_default="0"),
        sa.Column("ctl", sa.Float(), server_default="0"),
        sa.Column("atl", sa.Float(), server_default="0"),
        sa.Column("tsb", sa.Float(), server_default="0"),
        sa.UniqueConstraint("athlete_id", "date", name="uq_load_athlete_date"),
    )
    op.create_index("ix_daily_load_athlete_id", "daily_load", ["athlete_id"])
    op.create_index("ix_daily_load_date", "daily_load", ["date"])

    op.create_table(
        "plan",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "athlete_id",
            sa.Integer(),
            sa.ForeignKey("athlete.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("goal_time_s", sa.Integer(), nullable=False),
        sa.Column("race_date", sa.Date(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("weeks", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("engine_version", sa.String(length=32), nullable=False),
        sa.Column("superseded_by", sa.Integer(), sa.ForeignKey("plan.id", ondelete="SET NULL")),
    )
    op.create_index("ix_plan_athlete_id", "plan", ["athlete_id"])

    op.create_table(
        "plan_session",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "plan_id", sa.Integer(), sa.ForeignKey("plan.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("week_no", sa.Integer(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("session_type", sa.String(length=40), nullable=False),
        sa.Column("target_distance_m", sa.Float()),
        sa.Column("target_pace_low", sa.Float()),
        sa.Column("target_pace_high", sa.Float()),
        sa.Column("structure", postgresql.JSONB()),
        sa.Column("notes", sa.Text()),
        sa.Column("status", sa.String(length=16), server_default="planned"),
        sa.Column(
            "matched_activity_id",
            sa.Integer(),
            sa.ForeignKey("activity.id", ondelete="SET NULL"),
        ),
    )
    op.create_index("ix_plan_session_plan_id", "plan_session", ["plan_id"])
    op.create_index("ix_plan_session_date", "plan_session", ["date"])

    op.create_table(
        "coach_message",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "athlete_id",
            sa.Integer(),
            sa.ForeignKey("athlete.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("context_snapshot", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_coach_message_athlete_id", "coach_message", ["athlete_id"])
    op.create_index("ix_coach_message_created_at", "coach_message", ["created_at"])


def downgrade() -> None:
    for table in (
        "coach_message",
        "plan_session",
        "plan",
        "daily_load",
        "best_effort",
        "activity_stream",
        "activity",
        "oauth_token",
        "athlete",
    ):
        op.drop_table(table)
