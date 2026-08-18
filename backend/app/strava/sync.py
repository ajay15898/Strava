"""Backfill, incremental sync, normalization and deduplication.

The dedup and richness functions are pure and operate on plain dicts so they can
be tested against real history without a database.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import (
    DUPLICATE_DISTANCE_TOLERANCE,
    DUPLICATE_WINDOW_S,
    RUN_SPORT_TYPES,
)
from app.models import Activity, Athlete, BestEffort
from app.strava.client import StravaClient
from app.strava.oauth import valid_access_token

log = logging.getLogger(__name__)

# Activity detail is one request each; fetch it only for runs long enough to
# contribute a meaningful best-effort point to the pace-at-distance curve.
DETAIL_MIN_DISTANCE_M = 3000.0

# Fields whose presence indicates the richer of two duplicate recordings.
RICHNESS_FIELDS = (
    "calories",
    "avg_hr",
    "avg_watts",
    "avg_cadence",
    "elevation_gain_m",
    "polyline",
    "relative_effort",
)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def normalize_activity(raw: dict[str, Any]) -> dict[str, Any]:
    """Map a Strava activity payload (summary or detail) onto our columns."""
    start_local = _parse_dt(raw.get("start_date_local"))
    start_utc = _parse_dt(raw.get("start_date"))
    if start_local is not None and start_local.tzinfo is not None:
        start_local = start_local.replace(tzinfo=None)

    calories = raw.get("calories")
    if calories is None and raw.get("kilojoules") is not None:
        # Summary payloads carry kilojoules instead; for running these are
        # close enough to kcal to serve as a richness signal, which is all we
        # use them for. Never surfaced as a metric.
        calories = raw.get("kilojoules")

    return {
        "strava_id": int(raw["id"]),
        "sport_type": raw.get("sport_type") or raw.get("type") or "Unknown",
        "name": raw.get("name"),
        "start_local": start_local,
        "start_utc": start_utc,
        "distance_m": float(raw.get("distance") or 0.0),
        "moving_time_s": int(raw.get("moving_time") or 0),
        "elapsed_time_s": int(raw.get("elapsed_time") or 0),
        "elevation_gain_m": raw.get("total_elevation_gain"),
        "avg_speed": raw.get("average_speed"),
        "max_speed": raw.get("max_speed"),
        "avg_hr": raw.get("average_heartrate"),
        "max_hr": raw.get("max_heartrate"),
        "has_heartrate": bool(raw.get("has_heartrate", False)),
        "avg_watts": raw.get("average_watts"),
        "has_device_watts": bool(raw.get("device_watts", False)),
        "avg_cadence": raw.get("average_cadence"),
        "calories": calories,
        "relative_effort": raw.get("suffer_score"),
        "pr_count": raw.get("pr_count"),
        "achievement_count": raw.get("achievement_count"),
        "gear_id": raw.get("gear_id"),
        "polyline": (raw.get("map") or {}).get("summary_polyline"),
    }


def richness_score(rec: dict[str, Any]) -> int:
    """How complete a recording is, for choosing between duplicates.

    A device that logged heart rate, calories and power is more useful than one
    that logged 70 m more distance, so field completeness wins over distance.
    """
    return sum(1 for f in RICHNESS_FIELDS if rec.get(f) not in (None, "", 0))


def find_duplicate_clusters(records: Iterable[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group records that are the same run recorded twice.

    Same sport_type, start within DUPLICATE_WINDOW_S, distance within
    DUPLICATE_DISTANCE_TOLERANCE. Returns only clusters of 2 or more.
    """
    ordered = sorted(
        (r for r in records if r.get("start_local") is not None),
        key=lambda r: (r["start_local"], r["strava_id"]),
    )
    clustered: set[int] = set()
    clusters: list[list[dict[str, Any]]] = []

    for i, seed in enumerate(ordered):
        if seed["strava_id"] in clustered:
            continue
        cluster = [seed]
        for other in ordered[i + 1 :]:
            if other["strava_id"] in clustered:
                continue
            gap = abs((other["start_local"] - seed["start_local"]).total_seconds())
            if gap > DUPLICATE_WINDOW_S:
                break
            if other["sport_type"] != seed["sport_type"]:
                continue
            widest = max(other["distance_m"], seed["distance_m"])
            if widest <= 0:
                continue
            if abs(other["distance_m"] - seed["distance_m"]) / widest > DUPLICATE_DISTANCE_TOLERANCE:
                continue
            cluster.append(other)

        if len(cluster) > 1:
            for rec in cluster:
                clustered.add(rec["strava_id"])
            clusters.append(cluster)

    return clusters


def choose_keeper(cluster: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick the survivor: richest recording, then longest, then lowest id."""
    return max(
        cluster,
        key=lambda r: (richness_score(r), r["distance_m"], -r["strava_id"]),
    )


def resolve_duplicates(
    records: Iterable[dict[str, Any]],
) -> dict[int, int]:
    """Map each duplicate strava_id to the strava_id that supersedes it."""
    mapping: dict[int, int] = {}
    for cluster in find_duplicate_clusters(records):
        keeper = choose_keeper(cluster)
        for rec in cluster:
            if rec["strava_id"] != keeper["strava_id"]:
                mapping[rec["strava_id"]] = keeper["strava_id"]
    return mapping


# --- database-facing ------------------------------------------------------


def upsert_activity(db: Session, athlete_id: int, rec: dict[str, Any]) -> Activity:
    activity = db.scalar(select(Activity).where(Activity.strava_id == rec["strava_id"]))
    if activity is None:
        activity = Activity(athlete_id=athlete_id, strava_id=rec["strava_id"])
        db.add(activity)

    for key, value in rec.items():
        if key == "strava_id":
            continue
        # A summary payload must never null out a field a detail payload filled.
        if value is None and getattr(activity, key, None) is not None:
            continue
        setattr(activity, key, value)
    return activity


def apply_dedup(db: Session, athlete_id: int) -> int:
    """Recompute duplicate flags across the athlete's whole history.

    Idempotent and always run over the full set, because a newly arrived
    activity can be the duplicate of one ingested weeks ago.
    """
    activities = list(
        db.scalars(select(Activity).where(Activity.athlete_id == athlete_id)).all()
    )
    records = [
        {
            "strava_id": a.strava_id,
            "sport_type": a.sport_type,
            "start_local": a.start_local,
            "distance_m": a.distance_m,
            "calories": a.calories,
            "avg_hr": a.avg_hr,
            "avg_watts": a.avg_watts,
            "avg_cadence": a.avg_cadence,
            "elevation_gain_m": a.elevation_gain_m,
            "polyline": a.polyline,
            "relative_effort": a.relative_effort,
        }
        for a in activities
    ]
    mapping = resolve_duplicates(records)

    for activity in activities:
        superseded_by = mapping.get(activity.strava_id)
        activity.is_duplicate = superseded_by is not None
        activity.duplicate_of_strava_id = superseded_by

    db.commit()
    log.info("dedup: flagged %s duplicate activities", len(mapping))
    return len(mapping)


def store_best_efforts(db: Session, activity: Activity, detail: dict[str, Any]) -> int:
    efforts = detail.get("best_efforts") or []
    stored = 0
    for raw in efforts:
        effort_type = raw.get("name")
        if not effort_type:
            continue
        existing = db.scalar(
            select(BestEffort).where(
                BestEffort.activity_id == activity.id,
                BestEffort.effort_type == effort_type,
            )
        )
        if existing is None:
            existing = BestEffort(activity_id=activity.id, effort_type=effort_type)
            db.add(existing)
        existing.strava_effort_id = raw.get("id")
        existing.duration_s = int(raw.get("moving_time") or raw.get("elapsed_time") or 0)
        existing.distance_m = float(raw.get("distance") or 0.0)
        stored += 1
    return stored


def backfill(
    db: Session,
    athlete: Athlete,
    *,
    after: datetime | None = None,
    fetch_details: bool = True,
) -> dict[str, int]:
    """Import history, then dedup, then pull detail for substantial runs."""
    token = valid_access_token(db, athlete)
    after_ts = int(after.replace(tzinfo=UTC).timestamp()) if after else None

    imported = 0
    page = 1
    with StravaClient(token) as client:
        while True:
            batch = client.activities(after=after_ts, page=page, per_page=100)
            if not batch:
                break
            for raw in batch:
                upsert_activity(db, athlete.id, normalize_activity(raw))
                imported += 1
            db.commit()
            log.info("backfill page %s: %s activities", page, len(batch))
            page += 1

    duplicates = apply_dedup(db, athlete.id)
    details = fetch_activity_details(db, athlete) if fetch_details else 0

    return {"imported": imported, "duplicates": duplicates, "details": details}


def fetch_activity_details(db: Session, athlete: Athlete) -> int:
    """Pull detail (and therefore best efforts) for runs above the threshold.

    Detail is one request per activity, so this is deliberately restricted to
    non-duplicate runs long enough to matter to the pace curve.
    """
    pending = list(
        db.scalars(
            select(Activity).where(
                Activity.athlete_id == athlete.id,
                Activity.is_duplicate.is_(False),
                Activity.sport_type.in_(RUN_SPORT_TYPES),
                Activity.distance_m >= DETAIL_MIN_DISTANCE_M,
                Activity.streams_fetched.is_(False),
            )
        ).all()
    )
    if not pending:
        return 0

    token = valid_access_token(db, athlete)
    fetched = 0
    with StravaClient(token) as client:
        for activity in pending:
            try:
                detail = client.activity(activity.strava_id)
            except Exception:
                log.exception("detail fetch failed for %s", activity.strava_id)
                continue
            for key, value in normalize_activity(detail).items():
                if key == "strava_id" or value is None:
                    continue
                setattr(activity, key, value)
            store_best_efforts(db, activity, detail)
            activity.streams_fetched = True
            fetched += 1
            db.commit()

    log.info("fetched detail for %s activities", fetched)
    return fetched


def incremental(db: Session, athlete: Athlete) -> dict[str, int]:
    """Sync only what has appeared since the newest activity we hold."""
    newest = db.scalar(
        select(Activity.start_utc)
        .where(Activity.athlete_id == athlete.id)
        .order_by(Activity.start_utc.desc())
        .limit(1)
    )
    return backfill(db, athlete, after=newest)
