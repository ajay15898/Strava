"""Strava OAuth2 authorization-code flow.

Two things Strava does that bite if ignored:
  1. Refresh tokens rotate. Every refresh response may carry a *new*
     refresh_token, and the old one stops working. It must be persisted.
  2. Access tokens are short-lived (6 h). Anything holding a token for the
     length of a backfill must re-check expiry mid-run, not just at the start.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Athlete, OAuthToken

log = logging.getLogger(__name__)

AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"

SCOPES = "activity:read_all,profile:read_all"

# Refresh when the token expires inside this margin rather than waiting for a
# 401 — a long backfill can otherwise cross the boundary mid-page.
REFRESH_MARGIN = timedelta(minutes=5)


def authorize_url(state: str = "") -> str:
    s = get_settings()
    params = {
        "client_id": s.strava_client_id,
        "redirect_uri": s.strava_redirect_uri,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": SCOPES,
    }
    if state:
        params["state"] = state
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def _post_token(payload: dict) -> dict:
    s = get_settings()
    payload = {
        "client_id": s.strava_client_id,
        "client_secret": s.strava_client_secret,
        **payload,
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(TOKEN_URL, data=payload)
    resp.raise_for_status()
    return resp.json()


def exchange_code(db: Session, code: str) -> Athlete:
    """Exchange an authorization code, creating or updating the athlete."""
    data = _post_token({"code": code, "grant_type": "authorization_code"})

    raw = data.get("athlete") or {}
    strava_id = raw.get("id")
    if strava_id is None:
        raise ValueError("Strava token response contained no athlete id")

    athlete = db.query(Athlete).filter_by(strava_id=strava_id).one_or_none()
    if athlete is None:
        athlete = Athlete(strava_id=strava_id)
        db.add(athlete)

    name = " ".join(p for p in (raw.get("firstname"), raw.get("lastname")) if p)
    athlete.name = name or athlete.name
    athlete.measurement_pref = raw.get("measurement_preference") or "metric"

    _store_token(db, athlete, data)
    db.commit()
    return athlete


def _store_token(db: Session, athlete: Athlete, data: dict) -> OAuthToken:
    expires_at = datetime.fromtimestamp(data["expires_at"], tz=UTC)

    if athlete.id is None:
        db.flush()

    token = db.query(OAuthToken).filter_by(athlete_id=athlete.id).one_or_none()
    if token is None:
        token = OAuthToken(athlete_id=athlete.id)
        db.add(token)

    token.access_token = data["access_token"]
    # Rotated on every refresh — persisting the old one locks the account out.
    token.refresh_token = data["refresh_token"]
    token.expires_at = expires_at
    token.scope = data.get("scope") or token.scope
    return token


def valid_access_token(db: Session, athlete: Athlete) -> str:
    """Return a live access token, refreshing if it expires within the margin."""
    token = athlete.token or db.query(OAuthToken).filter_by(athlete_id=athlete.id).one_or_none()
    if token is None:
        raise LookupError(f"no OAuth token stored for athlete {athlete.id}")

    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if expires_at - REFRESH_MARGIN > datetime.now(UTC):
        return token.access_token

    log.info("refreshing Strava token for athlete %s", athlete.id)
    data = _post_token(
        {"refresh_token": token.refresh_token, "grant_type": "refresh_token"}
    )
    _store_token(db, athlete, data)
    db.commit()
    return data["access_token"]
