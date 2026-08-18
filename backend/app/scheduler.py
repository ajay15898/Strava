"""Background incremental sync.

Strava webhooks need a publicly reachable callback, which means a tunnel in
development. Polling every few minutes costs one list request and gets the same
result without that dependency — at 20-minute intervals it is roughly 72
requests a day against a 1000/day read budget.

The loop is deliberately dumb: it never raises into the event loop, and a
failure is logged and retried on the next tick rather than killing the task.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone

from app.constants import SYNC_INTERVAL_MINUTES
from app.db import SessionLocal
from app.models import Athlete
from app.planner import service as plan_service
from app.strava import sync

log = logging.getLogger(__name__)

#: Set by the loop so /api/health can report whether sync is actually alive.
last_run: dict[str, object] = {"at": None, "result": None, "error": None}


def run_once() -> dict[str, object]:
    """One incremental sync, then reconcile the live plan against it."""
    db = SessionLocal()
    try:
        athlete = db.query(Athlete).order_by(Athlete.id).first()
        if athlete is None:
            return {"skipped": "no athlete connected"}

        result = dict(sync.incremental(db, athlete))

        plan = plan_service.current_plan(db, athlete.id)
        if plan is not None:
            result["compliance"] = plan_service.reconcile(db, athlete, plan)
        return result
    finally:
        db.close()


#: Short grace period before the first tick so a restart does not fire a sync
#: while the app is still coming up, but the dashboard is still current within
#: a minute of boot rather than waiting out a full interval.
STARTUP_DELAY_S = 20


async def _loop(interval_minutes: int) -> None:
    delay = STARTUP_DELAY_S
    while True:
        try:
            await asyncio.sleep(delay)
            delay = interval_minutes * 60
            result = await asyncio.to_thread(run_once)
            last_run.update(
                {"at": datetime.now(timezone.utc).isoformat(), "result": result, "error": None}
            )
            log.info("background sync: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — a bad tick must not kill the loop
            last_run.update(
                {"at": datetime.now(timezone.utc).isoformat(), "result": None, "error": str(exc)}
            )
            log.exception("background sync failed; retrying next tick")


def start(interval_minutes: int = SYNC_INTERVAL_MINUTES) -> asyncio.Task:
    return asyncio.create_task(_loop(interval_minutes), name="pace-sync")
