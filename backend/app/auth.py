"""
Auth — password hashing, JWT issue/verify, and the FastAPI dependency
every protected endpoint uses to find out which workspace is asking.

Design choices, and why:

- **Bearer token (Authorization header), not a cookie.** The deployment
  target is frontend on Vercel + backend on Render — two different
  origins. Cross-origin cookies need SameSite=None; Secure and careful
  CORS credential handling to work at all, and even then browsers are
  increasingly restrictive about third-party cookies. A JWT the frontend
  stores itself and attaches as `Authorization: Bearer <token>` sidesteps
  all of that — it's an explicit header on an explicit fetch call, not
  something the browser has to be persuaded to send automatically.

- **JWT, not server-side sessions.** No session table to manage, no
  server-side state to clean up — the token itself carries what's needed
  (user id) and is verified by signature + expiry on every request. For
  this project's scale, that's simpler than it is limiting.

- **What this deliberately does NOT do:** refresh token rotation, email
  verification, password reset flows, rate limiting on login attempts,
  or any role/permission system beyond "you're a member of exactly one
  workspace." AGENTS.md section 5 lists "Complex role hierarchy" and
  "Enterprise SSO" as explicit non-goals — this auth system is sized to
  match that: real (bcrypt hashing, signed/expiring tokens, workspace
  isolation actually enforced), but intentionally not enterprise-grade.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import User, Workspace

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Malformed hash (shouldn't happen in practice) — fail closed, not open.
        return False


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str) -> int:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired, please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    try:
        return int(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid authentication token")


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Every protected endpoint depends on this (directly or via
    get_current_workspace_id below) to find out who's asking.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    user_id = _decode_token(token)

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user


def get_current_workspace_id(user: User = Depends(get_current_user)) -> int:
    """The dependency nearly every domain endpoint in main.py actually
    uses — most queries only need the id to filter by, not the full User
    object.
    """
    return user.workspace_id


def get_current_workspace(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Workspace:
    workspace = db.get(Workspace, user.workspace_id)
    if workspace is None:
        raise HTTPException(status_code=401, detail="Workspace no longer exists")
    return workspace
