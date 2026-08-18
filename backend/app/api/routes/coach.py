from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_athlete
from app.coach import context as context_mod, service
from app.db import get_db
from app.models import Athlete

router = APIRouter(prefix="/api/coach", tags=["coach"])


class Question(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class Reply(BaseModel):
    content: str
    verified: bool
    used_fallback: bool
    attempts: int
    violations: list[str]
    model: str


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime


@router.post("/message", response_model=Reply)
def ask(
    question: Question,
    athlete: Athlete = Depends(current_athlete),
    db: Session = Depends(get_db),
) -> Reply:
    try:
        reply = service.ask(db, athlete, question.message)
    except service.CoachUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Reply(**vars(reply))


@router.get("/history", response_model=list[MessageOut])
def history(
    athlete: Athlete = Depends(current_athlete), db: Session = Depends(get_db)
) -> list[MessageOut]:
    return [MessageOut.model_validate(m, from_attributes=True) for m in service.history(db, athlete.id)]


@router.get("/context", response_model=dict)
def get_context(
    athlete: Athlete = Depends(current_athlete), db: Session = Depends(get_db)
) -> dict:
    """The exact object the model is given. Exposed because a coach whose
    inputs cannot be inspected cannot be audited."""
    return context_mod.build(db, athlete)


@router.post("/reverify/{message_id}", response_model=dict)
def reverify(
    message_id: int,
    athlete: Athlete = Depends(current_athlete),
    db: Session = Depends(get_db),
) -> dict:
    """Re-run the numeric guard over a stored answer, against the snapshot it
    was actually given rather than against today's numbers."""
    result = service.reverify(db, message_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No verifiable message with that id")
    return {"ok": result.ok, "violations": [str(v) for v in result.violations]}
