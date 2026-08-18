"""Shared helpers.

These tests deliberately need no database. Every function under test is either
pure or operates on model instances, and SQLAlchemy models can be constructed
in memory without a session — so the baseline is provable in milliseconds with
no Postgres running.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.constants import NOISE_FLOOR_M, RUN_SPORT_TYPES
from app.models import Activity
from app.strava.sync import normalize_activity, resolve_duplicates
from tests.fixtures import strava_activities

BASELINE_START = date(2026, 3, 14)
BASELINE_END = date(2026, 8, 16)


@pytest.fixture(scope="session")
def normalized() -> list[dict]:
    return [normalize_activity(raw) for raw in strava_activities()]


@pytest.fixture(scope="session")
def duplicate_map(normalized) -> dict[int, int]:
    return resolve_duplicates(normalized)


@pytest.fixture(scope="session")
def runs(normalized, duplicate_map) -> list[Activity]:
    """The analysable runs — exactly what `analytics.base.valid_runs` returns."""
    out = [
        Activity(**rec)
        for rec in normalized
        if rec["strava_id"] not in duplicate_map
        and rec["sport_type"] in RUN_SPORT_TYPES
        and rec["distance_m"] >= NOISE_FLOOR_M
        and BASELINE_START <= rec["start_local"].date() <= BASELINE_END
    ]
    return sorted(out, key=lambda a: a.start_local)
