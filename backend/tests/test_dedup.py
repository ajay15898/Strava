"""Deduplication against the three real duplicate pairs in the history."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.strava.sync import (
    choose_keeper,
    find_duplicate_clusters,
    richness_score,
    resolve_duplicates,
)


def test_finds_exactly_three_clusters(normalized):
    clusters = find_duplicate_clusters(normalized)
    dates = sorted(c[0]["start_local"].date().isoformat() for c in clusters)
    assert dates == ["2026-03-14", "2026-03-15", "2026-06-04"]
    assert all(len(c) == 2 for c in clusters)


def test_keeps_the_richer_recording(duplicate_map):
    # In every pair the discarded record is the one Strava stored without
    # calories, even though it logged slightly more distance.
    assert duplicate_map == {
        17720996478: 17720996766,
        17728305812: 17728303589,
        18779723440: 18779721036,
    }


def test_richness_prefers_completeness_over_distance(normalized):
    by_id = {r["strava_id"]: r for r in normalized}
    longer, richer = by_id[18779723440], by_id[18779721036]
    assert longer["distance_m"] > richer["distance_m"]
    assert richness_score(richer) > richness_score(longer)
    assert choose_keeper([longer, richer])["strava_id"] == richer["strava_id"]


def test_genuine_back_to_back_runs_are_not_merged(duplicate_map):
    """2026-03-17 has two real runs 23 min apart — 5173 m then 1638 m.

    Well inside the 300 s window would not save them; the distance guard is
    what keeps them distinct.
    """
    assert 17756377730 not in duplicate_map
    assert 17756382839 not in duplicate_map


def test_widened_window_still_catches_the_112_second_pair(duplicate_map):
    """The 2026-03-14 pair is 112 s apart — only 8 s inside the original
    120 s window. It must remain caught after the widening."""
    assert duplicate_map[17720996478] == 17720996766


def test_dedup_is_idempotent(normalized, duplicate_map):
    assert resolve_duplicates(normalized) == duplicate_map


@pytest.mark.parametrize(
    "gap_s,expected",
    [(0, True), (299, True), (301, False)],
)
def test_window_boundary(gap_s, expected):
    base = datetime(2026, 5, 1, 8, 0, 0)
    records = [
        {
            "strava_id": 1,
            "sport_type": "Run",
            "start_local": base,
            "distance_m": 5000.0,
            "calories": 300,
        },
        {
            "strava_id": 2,
            "sport_type": "Run",
            "start_local": base + timedelta(seconds=gap_s),
            "distance_m": 5000.0,
            "calories": None,
        },
    ]
    assert bool(resolve_duplicates(records)) is expected


def test_different_sports_never_merge():
    base = datetime(2026, 5, 1, 8, 0, 0)
    records = [
        {"strava_id": 1, "sport_type": "Run", "start_local": base, "distance_m": 5000.0},
        {"strava_id": 2, "sport_type": "Walk", "start_local": base, "distance_m": 5000.0},
    ]
    assert resolve_duplicates(records) == {}
