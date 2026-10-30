"""
Authentication & Access Control Endpoints
Provides user login, session management, user management, and API key lifecycle.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import models
from app.database.db_manager import get_db
from app.auth import Identity, get_identity, require_admin
from app.services.auth_security import (
    hash_password,
    verify_password,
    generate_api_key,
    generate_session_token,
    generate_recovery_token,
    hash_api_key,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# Schemas
class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_at: str
    user: dict


class UserCreate(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="editor", pattern="^(admin|editor|viewer)$")


class UserResponse(BaseModel):
    id: int
    tenant_id: str
    email: str
    name: str
    role: str
    is_active: bool
    created_at: str
    last_login_at: Optional[str] = None


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    role: str = Field(default="editor", pattern="^(admin|editor|viewer)$")
    expires_in_days: Optional[int] = Field(default=90, ge=1, le=365)


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    role: str
    is_active: bool
    created_at: str
    last_used_at: Optional[str] = None
    expires_at: Optional[str] = None
    raw_key: Optional[str] = None  # Returned only upon creation


# Public Endpoint: Login
@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Authenticate user with email and password, returning an active session token."""
    email = payload.email.lower()
    ip = request.client.host if request.client else "unknown"
    if _login_throttled(db, email, ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts; try again later",
        )
    user = db.query(models.User).filter_by(email=email).first()
    valid = bool(user and user.is_active
                 and verify_password(payload.password, user.password_hash))
    if not valid:
        _record_login_attempt(db, email, ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    _clear_login_failures(db, email)
    # Update last login timestamp
    now = datetime.now(timezone.utc)
    user.last_login_at = now

    # Create session token
    raw_token, token_hash = generate_session_token()
    expires_at = now + timedelta(hours=settings.AUTH_TOKEN_EXPIRE_HOURS)
    session = models.UserSession(
        tenant_id=user.tenant_id,
        user_id=user.id,
        token_hash=token_hash,
        created_at=now,
        expires_at=expires_at,
        is_revoked=False,
    )
    db.add(session)
    db.commit()

    return {
        "token": raw_token,
        "token_type": "bearer",
        "expires_at": expires_at.isoformat(),
        "user": {
            "id": user.id,
            "tenant_id": user.tenant_id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
        },
    }


# Protected: Current User Profile
@router.get("/me")
def get_current_user_profile(
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
):
    """Get profile information for currently authenticated actor."""
    profile = {
        "actor": identity.actor,
        "tenant_id": identity.tenant_id,
        "role": identity.role,
    }
    if identity.user_id:
        user = db.get(models.User, identity.user_id)
        if user:
            profile.update({
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            })
    return profile


# Protected: Logout
@router.post("/logout")
def logout(
    request: Request,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
):
    """Revoke current active session token."""
    raw_token = ""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        raw_token = auth_header[7:].strip()
    elif request.headers.get("X-RECOVERFLOW-API-KEY"):
        raw_token = request.headers.get("X-RECOVERFLOW-API-KEY", "")

    if raw_token:
        token_hash = hash_api_key(raw_token)
        session = db.query(models.UserSession).filter_by(token_hash=token_hash).first()
        if session:
            session.is_revoked = True
            db.commit()
    return {"status": "logged_out"}


# Admin Only: List Users
@router.get("/users")
def list_users(
    identity: Identity = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all registered users for current tenant."""
    users = db.query(models.User).filter_by(tenant_id=identity.tenant_id).order_by(models.User.id).all()
    return [
        {
            "id": u.id,
            "tenant_id": u.tenant_id,
            "email": u.email,
            "name": u.name,
            "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        }
        for u in users
    ]


# Admin Only: Create User
@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    identity: Identity = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new staff user with hashed password."""
    existing = db.query(models.User).filter_by(email=payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="User with this email already exists")

    new_user = models.User(
        tenant_id=identity.tenant_id,
        email=payload.email.lower(),
        name=payload.name,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {
        "id": new_user.id,
        "tenant_id": new_user.tenant_id,
        "email": new_user.email,
        "name": new_user.name,
        "role": new_user.role,
        "is_active": new_user.is_active,
        "created_at": new_user.created_at.isoformat(),
    }


# Admin Only: Generate API Key
@router.post("/keys", status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: ApiKeyCreate,
    identity: Identity = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Generate a new API key. Raw key is returned once only upon creation."""
    raw_key, key_prefix, key_hash = generate_api_key(prefix="rf")
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=payload.expires_in_days) if payload.expires_in_days else None

    api_key = models.UserApiKey(
        tenant_id=identity.tenant_id,
        user_id=identity.user_id,
        name=payload.name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        role=payload.role,
        is_active=True,
        created_at=now,
        expires_at=expires_at,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return {
        "id": api_key.id,
        "name": api_key.name,
        "key_prefix": api_key.key_prefix,
        "role": api_key.role,
        "is_active": api_key.is_active,
        "created_at": api_key.created_at.isoformat(),
        "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
        "raw_key": raw_key,
    }


# Admin Only: List API Keys
@router.get("/keys")
def list_api_keys(
    identity: Identity = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all API keys for tenant (hashes are never returned)."""
    keys = db.query(models.UserApiKey).filter_by(tenant_id=identity.tenant_id).order_by(models.UserApiKey.id).all()
    return [
        {
            "id": k.id,
            "name": k.name,
            "key_prefix": k.key_prefix,
            "role": k.role,
            "is_active": k.is_active,
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
        }
        for k in keys
    ]


# Admin Only: Revoke API Key
@router.delete("/keys/{key_id}")
def revoke_api_key(
    key_id: int,
    identity: Identity = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Revoke an API key."""
    key = db.query(models.UserApiKey).filter_by(id=key_id, tenant_id=identity.tenant_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    key.is_active = False
    db.commit()
    return {"status": "revoked", "id": key_id}


LOGIN_EMAIL_LIMIT = 5
LOGIN_IP_LIMIT = 20
LOGIN_WINDOW_MINUTES = 15


def _naive_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _login_throttled(db: Session, email: str, ip: str) -> bool:
    now = _naive_utc()
    since = now - timedelta(minutes=LOGIN_WINDOW_MINUTES)
    db.query(models.LoginAttempt).filter(
        models.LoginAttempt.created_at < now - timedelta(hours=24)).delete()
    email_fails = db.query(models.LoginAttempt).filter(
        models.LoginAttempt.email == email,
        models.LoginAttempt.success.is_(False),
        models.LoginAttempt.created_at >= since).count()
    if email_fails >= LOGIN_EMAIL_LIMIT:
        db.commit()
        return True
    ip_fails = db.query(models.LoginAttempt).filter(
        models.LoginAttempt.ip == ip,
        models.LoginAttempt.success.is_(False),
        models.LoginAttempt.created_at >= since).count()
    db.commit()
    return ip_fails >= LOGIN_IP_LIMIT


def _record_login_attempt(db: Session, email: str, ip: str) -> None:
    db.add(models.LoginAttempt(email=email, ip=ip, success=False))
    db.commit()


def _clear_login_failures(db: Session, email: str) -> None:
    db.query(models.LoginAttempt).filter(
        models.LoginAttempt.email == email,
        models.LoginAttempt.success.is_(False)).delete()
    db.commit()


def _raw_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return (request.headers.get("X-RECOVERFLOW-API-KEY", "") or
            request.headers.get("X-APEX-API-KEY", ""))


# Protected: Rotate Session
@router.post("/rotate")
def rotate_session(
    request: Request,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
):
    """Swap the current session token for a fresh one; the old token dies."""
    raw = _raw_token(request)
    session = db.query(models.UserSession).filter_by(
        token_hash=hash_api_key(raw), is_revoked=False).first() if raw else None
    if not session:
        raise HTTPException(status_code=409,
                            detail="Only active session tokens rotate; API keys do not")
    now = datetime.now(timezone.utc)
    session.is_revoked = True
    raw_token, token_hash = generate_session_token()
    expires_at = now + timedelta(hours=settings.AUTH_TOKEN_EXPIRE_HOURS)
    db.add(models.UserSession(
        tenant_id=session.tenant_id, user_id=session.user_id,
        token_hash=token_hash, created_at=now, expires_at=expires_at,
        is_revoked=False))
    db.add(models.AuditEvent(tenant_id=session.tenant_id, actor=identity.actor,
                             action="session_rotated", entity_type="user_session",
                             entity_id=str(session.id)))
    db.commit()
    return {"token": raw_token, "token_type": "bearer",
            "expires_at": expires_at.isoformat()}


# Protected: List Own Sessions
@router.get("/sessions")
def list_sessions(
    request: Request,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
):
    """List the caller's sessions. Token values are never returned."""
    if not identity.user_id:
        raise HTTPException(status_code=409, detail="API keys have no sessions")
    raw = _raw_token(request)
    current = hash_api_key(raw) if raw else None
    rows = db.query(models.UserSession).filter_by(
        user_id=identity.user_id).order_by(models.UserSession.id.desc()).all()
    return [{"id": row.id,
             "created_at": row.created_at.isoformat() if row.created_at else None,
             "expires_at": row.expires_at.isoformat() if row.expires_at else None,
             "is_revoked": row.is_revoked,
             "current": bool(current) and row.token_hash == current}
            for row in rows]


# Protected: Revoke One Session
@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: int,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
):
    """Revoke one of the caller's own sessions (idempotent)."""
    row = db.query(models.UserSession).filter_by(
        id=session_id, user_id=identity.user_id or -1).first()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    row.is_revoked = True
    db.commit()
    return {"status": "revoked", "id": session_id}


# Protected: Revoke All Sessions
@router.post("/revoke-all")
def revoke_all_sessions(
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
):
    """Revoke every session of the caller, including the current one."""
    if not identity.user_id:
        raise HTTPException(status_code=409, detail="API keys have no sessions")
    rows = db.query(models.UserSession).filter_by(
        user_id=identity.user_id, is_revoked=False).all()
    for row in rows:
        row.is_revoked = True
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="sessions_revoked_all", entity_type="user",
                             entity_id=str(identity.user_id),
                             details=f"count={len(rows)}"))
    db.commit()
    return {"status": "revoked_all", "count": len(rows)}


class RecoverInput(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=8, max_length=128)


# Admin Only: Issue Recovery Token
@router.post("/users/{user_id}/recovery", status_code=status.HTTP_201_CREATED)
def issue_recovery(
    user_id: int,
    identity: Identity = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Issue a single-use recovery token. The raw token is shown once only."""
    target = db.get(models.User, user_id)
    if not target or target.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="User not found")
    raw_token, token_hash = generate_recovery_token()
    now = datetime.now(timezone.utc)
    db.add(models.UserRecoveryToken(
        tenant_id=target.tenant_id, user_id=target.id, token_hash=token_hash,
        expires_at=now + timedelta(hours=1), created_by=identity.actor))
    db.add(models.AuditEvent(tenant_id=target.tenant_id, actor=identity.actor,
                             action="recovery_token_issued", entity_type="user",
                             entity_id=str(target.id), details="valid 1 hour"))
    db.commit()
    return {"user_id": target.id, "recovery_token": raw_token,
            "expires_at": (now + timedelta(hours=1)).isoformat()}


# Public: Redeem Recovery Token
@router.post("/recover")
def recover_account(payload: RecoverInput, db: Session = Depends(get_db)):
    """Reset a password with a recovery token; kills all user sessions."""
    row = db.query(models.UserRecoveryToken).filter_by(
        token_hash=hash_api_key(payload.token)).first()
    user = db.get(models.User, row.user_id) if row else None
    if (not row or row.used_at is not None or not user or not user.is_active
            or row.expires_at.replace(tzinfo=None) < _naive_utc()
            or user.tenant_id != row.tenant_id):
        raise HTTPException(status_code=422,
                            detail="Recovery token is invalid or expired")
    user.password_hash = hash_password(payload.new_password)
    row.used_at = datetime.now(timezone.utc)
    for session in db.query(models.UserSession).filter_by(
            user_id=user.id, is_revoked=False).all():
        session.is_revoked = True
    db.add(models.AuditEvent(tenant_id=user.tenant_id, actor=user.email,
                             action="password_recovered", entity_type="user",
                             entity_id=str(user.id)))
    db.commit()
    return {"status": "password_reset"}
