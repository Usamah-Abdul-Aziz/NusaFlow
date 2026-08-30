import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from .auth import create_access_token, get_current_user, hash_password, verify_password
from .database import get_db
from .models import User, Workspace

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "workspace"


def _unique_slug(db: Session, name: str) -> str:
    base = _slugify(name)
    slug = base
    suffix = 2
    while db.query(Workspace).filter(Workspace.slug == slug).first() is not None:
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


class SignupRequest(BaseModel):
    workspace_name: str = Field(..., min_length=2, max_length=120)
    display_name: str = Field(..., min_length=1, max_length=120)
    email: str
    password: str = Field(..., min_length=8, max_length=200)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("Not a valid email address")
        return v.lower()


class LoginRequest(BaseModel):
    email: str
    password: str


def _serialize_user(user: User) -> dict:
    return {"id": user.id, "email": user.email, "display_name": user.display_name}


def _serialize_workspace(workspace: Workspace) -> dict:
    return {"id": workspace.id, "name": workspace.name, "slug": workspace.slug, "is_demo": workspace.is_demo}


def _issue_token_response(user: User, workspace: Workspace) -> dict:
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": _serialize_user(user),
        "workspace": _serialize_workspace(workspace),
    }


@router.post("/signup")
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    """Creates a brand-new, EMPTY workspace (no synthetic data) — unlike
    the demo workspace, which is seeded once at startup. A person signing
    up gets their own blank slate, not a copy of the demo data.
    """
    if db.query(User).filter(User.email == payload.email).first() is not None:
        raise HTTPException(status_code=409, detail="An account with that email already exists")

    workspace = Workspace(name=payload.workspace_name, slug=_unique_slug(db, payload.workspace_name), is_demo=False)
    db.add(workspace)
    db.flush()

    user = User(
        workspace_id=workspace.id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.refresh(workspace)

    return _issue_token_response(user, workspace)


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        # Same message either way — don't reveal whether the email exists.
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    workspace = db.get(Workspace, user.workspace_id)
    return _issue_token_response(user, workspace)


@router.post("/demo")
def demo_login(db: Session = Depends(get_db)):
    """No credentials needed — logs in as the shared Demo User in the
    pre-seeded demo workspace. This is intentionally the SAME account for
    every visitor who clicks "Explore Demo": simpler than provisioning a
    fresh sandbox per visitor, at the cost of visitors sharing (and
    potentially seeing each other's edits to) demo state. See README for
    the reset-demo-data admin endpoint that mitigates this.
    """
    workspace = db.query(Workspace).filter(Workspace.is_demo.is_(True)).first()
    if workspace is None:
        raise HTTPException(status_code=503, detail="Demo workspace is not set up yet")
    user = db.query(User).filter(User.workspace_id == workspace.id).first()
    if user is None:
        raise HTTPException(status_code=503, detail="Demo workspace has no user configured")

    return _issue_token_response(user, workspace)


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    workspace = db.get(Workspace, user.workspace_id)
    return {"user": _serialize_user(user), "workspace": _serialize_workspace(workspace)}
