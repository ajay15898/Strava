from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import current_athlete
from app.config import get_settings
from app.db import get_db
from app.models import Athlete
from app.strava import oauth

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/strava/authorize")
def authorize() -> RedirectResponse:
    settings = get_settings()
    if not settings.strava_client_id:
        raise HTTPException(status_code=500, detail="STRAVA_CLIENT_ID is not configured")
    return RedirectResponse(oauth.authorize_url(state=secrets.token_urlsafe(16)))


@router.get("/strava/callback")
def callback(
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    if error:
        raise HTTPException(status_code=400, detail=f"Strava authorization failed: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    athlete = oauth.exchange_code(db, code)
    frontend = get_settings().frontend_origin

    # Deliberately not a redirect. Bouncing straight to FRONTEND_ORIGIN drops
    # the athlete on a dead port whenever the dev server is not running, with
    # no signal that the exchange actually worked. Confirm inline and link on.
    return HTMLResponse(
        f"""<!doctype html>
<meta charset="utf-8">
<title>Pace — connected</title>
<style>
  body {{ font: 16px/1.6 system-ui, sans-serif; max-width: 34rem;
         margin: 15vh auto; padding: 0 1.5rem; }}
  code {{ background: #8881; padding: .15em .4em; border-radius: 4px; }}
  .ok {{ color: #0a7; font-weight: 600; }}
</style>
<p class="ok">Connected to Strava.</p>
<p>Athlete <strong>{athlete.name or athlete.strava_id}</strong>
   (id {athlete.strava_id}) is now linked.</p>
<p>Next, import the history:</p>
<p><code>POST http://localhost:8000/api/sync/backfill</code></p>
<p style="margin-top:2rem">
  <a href="{frontend}">Open the dashboard &rarr;</a>
  &nbsp;·&nbsp;
  <a href="/docs">API docs</a>
</p>
"""
    )


@router.post("/refresh")
def refresh(
    athlete: Athlete = Depends(current_athlete), db: Session = Depends(get_db)
) -> dict[str, str]:
    oauth.valid_access_token(db, athlete)
    return {"status": "ok"}
