"""The coach service: context, model call, verification, persistence.

**On streaming.** The original spec said stream to the client. It does not, and
the reason is structural rather than laziness: verification needs the complete
response before any of it can be trusted, so streaming raw model output would
mean showing the athlete text that the verifier has not cleared — and possibly
retracting it mid-sentence. The guard is the entire justification for using a
free-tier model here, so it wins over the typing effect. The client can animate
the verified text if the feel matters.

**On cost.** A rejected answer costs a second call, so one question can be two
requests against the rate limit. At Groq's 30 RPM / 1000 RPD that is not close
to binding for one athlete, but it is why the fallback exists rather than
retrying indefinitely.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.coach import context as context_mod, prompt as prompt_mod, verify as verify_mod
from app.config import get_settings
from app.models import Athlete, CoachMessage

log = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 8


class CoachUnavailable(RuntimeError):
    """No provider configured, or the provider could not be reached."""


@dataclass
class CoachReply:
    content: str
    verified: bool
    used_fallback: bool
    attempts: int
    violations: list[str]
    model: str


def _call_model(messages: list[dict]) -> str:
    settings = get_settings()
    if not settings.coach_configured:
        raise CoachUnavailable(
            "No coach provider configured. Set COACH_API_KEY (and COACH_BASE_URL / "
            "COACH_MODEL) in .env — see backend/app/coach/README.md."
        )

    payload = {
        "model": settings.coach_model,
        "messages": messages,
        "temperature": settings.coach_temperature,
        "stream": False,
    }

    try:
        with httpx.Client(timeout=settings.coach_timeout_s) as client:
            response = client.post(
                f"{settings.coach_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.coach_api_key}"},
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise CoachUnavailable(f"Could not reach the coach provider: {exc}") from exc

    if response.status_code == 429:
        raise CoachUnavailable("Coach provider rate limit reached. Try again shortly.")
    if response.status_code >= 400:
        raise CoachUnavailable(
            f"Coach provider returned {response.status_code}: {response.text[:200]}"
        )

    body = response.json()
    try:
        return body["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError) as exc:
        raise CoachUnavailable(f"Unexpected response shape from provider: {body}") from exc


def _history(db: Session, athlete_id: int) -> list[dict]:
    rows = db.scalars(
        select(CoachMessage)
        .where(CoachMessage.athlete_id == athlete_id)
        .order_by(CoachMessage.created_at.desc())
        .limit(MAX_HISTORY_MESSAGES)
    ).all()
    return [{"role": r.role, "content": r.content} for r in reversed(rows)]


def ask(
    db: Session,
    athlete: Athlete,
    question: str,
    *,
    today: date | None = None,
) -> CoachReply:
    """One question, verified before it is returned or stored."""
    settings = get_settings()
    ctx = context_mod.build(db, athlete, today=today)
    messages = prompt_mod.build_messages(ctx, question, _history(db, athlete.id))

    attempts = 0
    violations: list[str] = []
    content = ""
    verified = False

    for attempt in range(2):
        attempts = attempt + 1
        content = _call_model(messages)
        result = verify_mod.verify(content, ctx)

        if result.ok:
            verified = True
            break

        violations = [str(v) for v in result.violations]
        log.warning("coach verification failed (attempt %s): %s", attempts, violations)
        if attempt == 0:
            messages = [*messages, {"role": "assistant", "content": content},
                        prompt_mod.retry_instruction(result.message())]

    used_fallback = not verified
    if used_fallback:
        # Twice rejected. Return the deterministic summary, which passes by
        # construction because every value in it came from the context.
        content = prompt_mod.templated_summary(ctx)
        log.warning("coach fell back to the templated summary")

    _persist(db, athlete.id, question, content, ctx)

    return CoachReply(
        content=content,
        verified=verified,
        used_fallback=used_fallback,
        attempts=attempts,
        violations=violations,
        model=settings.coach_model,
    )


def _persist(db: Session, athlete_id: int, question: str, answer: str, ctx: dict) -> None:
    """Store both turns, with the context snapshot on the answer.

    Keeping the snapshot is what lets a past answer be re-verified later against
    exactly the numbers it was given, rather than against today's fitness.
    """
    db.add(CoachMessage(athlete_id=athlete_id, role="user", content=question))
    db.add(
        CoachMessage(
            athlete_id=athlete_id,
            role="assistant",
            content=answer,
            context_snapshot=ctx,
        )
    )
    db.commit()


def history(db: Session, athlete_id: int, limit: int = 50) -> list[CoachMessage]:
    rows = db.scalars(
        select(CoachMessage)
        .where(CoachMessage.athlete_id == athlete_id)
        .order_by(CoachMessage.created_at.desc())
        .limit(limit)
    ).all()
    return list(reversed(rows))


def reverify(db: Session, message_id: int) -> verify_mod.Result | None:
    """Re-run the guard over a stored answer against its own snapshot."""
    message = db.get(CoachMessage, message_id)
    if message is None or message.role != "assistant" or not message.context_snapshot:
        return None
    return verify_mod.verify(message.content, message.context_snapshot)
