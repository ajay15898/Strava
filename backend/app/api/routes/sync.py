from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_athlete
from app.db import SessionLocal, get_db
from app.models import Athlete
from app.schemas.responses import SyncResultOut
from app.strava import sync

router = APIRouter(prefix="/api/sync", tags=["sync"])


def _run_backfill(athlete_id: int) -> None:
    """Background worker gets its own session — the request's is long gone."""
    db = SessionLocal()
    try:
        athlete = db.get(Athlete, athlete_id)
        if athlete is not None:
            sync.backfill(db, athlete)
    finally:
        db.close()


@router.post("/backfill")
def backfill(
    background: BackgroundTasks,
    athlete: Athlete = Depends(current_athlete),
) -> dict[str, str]:
    background.add_task(_run_backfill, athlete.id)
    return {"status": "started"}


@router.post("/incremental", response_model=SyncResultOut)
def incremental(
    athlete: Athlete = Depends(current_athlete), db: Session = Depends(get_db)
) -> SyncResultOut:
    return SyncResultOut(**sync.incremental(db, athlete))


@router.post("/dedup", response_model=dict)
def dedup(
    athlete: Athlete = Depends(current_athlete), db: Session = Depends(get_db)
) -> dict[str, int]:
    """Re-run deduplication across the whole history. Idempotent."""
    return {"duplicates": sync.apply_dedup(db, athlete.id)}
