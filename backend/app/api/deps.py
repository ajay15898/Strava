from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Athlete


def current_athlete(db: Session = Depends(get_db)) -> Athlete:
    """The connected athlete.

    Single-tenant by design — this is one person's training log. If that ever
    changes, this is the only place that needs a session lookup.
    """
    athlete = db.scalar(select(Athlete).order_by(Athlete.id).limit(1))
    if athlete is None:
        raise HTTPException(
            status_code=404, detail="No athlete connected. Visit /api/auth/strava/authorize."
        )
    return athlete
