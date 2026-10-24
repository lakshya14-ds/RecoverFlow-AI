"""API key & database-backed user identities for local and enterprise deployments."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, Request
from app.config import settings
from app.services.auth_security import hash_api_key


@dataclass(frozen=True)
class Identity:
    actor: str
    tenant_id: str
    role: str  # admin, editor, viewer
    user_id: Optional[int] = None


def configured_keys() -> list[tuple[str, Identity]]:
    """Static bootstrap keys defined via environment variables."""
    entries = []
    if settings.RECOVERFLOW_API_KEY:
        entries.append((settings.RECOVERFLOW_API_KEY, Identity("local_admin", "local", "admin")))
    if settings.APEX_API_KEY:
        entries.append((settings.APEX_API_KEY, Identity("local_admin", "local", "admin")))
    for key_mapping in (settings.RECOVERFLOW_API_KEYS_JSON, settings.APEX_API_KEYS_JSON):
        if not key_mapping:
            continue
        try:
            for item in json.loads(key_mapping):
                if item.get("role") not in ("admin", "editor", "viewer"):
                    raise ValueError("Invalid API key role")
                entries.append((item["key"], Identity(item["actor"], item["tenant_id"], item["role"])))
        except Exception:
            pass
    return entries


def authenticate(key: str) -> Identity | None:
    """
    Authenticate an API key or session token.
    Checks static environment keys first, then validates against database UserApiKey and UserSession tables.
    """
    if not key:
        return None

    # 1. Fast static environment key matching
    for expected, identity in configured_keys():
        if secrets.compare_digest(key, expected):
            return identity

    # 2. Database-backed lookup
    token_hash = hash_api_key(key)
    try:
        from app.database.db_manager import SessionLocal
        from app.database import models

        with SessionLocal() as db:
            # Check UserApiKey table
            api_key = db.query(models.UserApiKey).filter_by(key_hash=token_hash, is_active=True).first()
            if api_key:
                now = datetime.now(timezone.utc)
                if api_key.expires_at and api_key.expires_at.replace(tzinfo=timezone.utc) < now:
                    return None
                api_key.last_used_at = now
                db.commit()
                return Identity(
                    actor=f"key_{api_key.name}",
                    tenant_id=api_key.tenant_id,
                    role=api_key.role,
                    user_id=api_key.user_id,
                )

            # Check UserSession table
            session = db.query(models.UserSession).filter_by(token_hash=token_hash, is_revoked=False).first()
            if session:
                now = datetime.now(timezone.utc)
                if session.expires_at.replace(tzinfo=timezone.utc) < now:
                    return None
                user = db.get(models.User, session.user_id)
                if user and user.is_active:
                    return Identity(
                        actor=user.email,
                        tenant_id=user.tenant_id,
                        role=user.role,
                        user_id=user.id,
                    )
    except Exception:
        # Fall back gracefully if database is initializing
        return None

    return None


def get_identity(request: Request) -> Identity:
    """FastAPI dependency returning current authenticated identity."""
    identity = getattr(request.state, "identity", None)
    if not identity:
        raise HTTPException(status_code=401, detail="Authentication required")
    return identity


# RBAC Role Gate Dependencies
def require_admin(identity: Identity = Depends(get_identity)) -> Identity:
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail="Admin permission required")
    return identity


def require_editor(identity: Identity = Depends(get_identity)) -> Identity:
    if identity.role not in ("admin", "editor"):
        raise HTTPException(status_code=403, detail="Editor permission required")
    return identity


def require_viewer(identity: Identity = Depends(get_identity)) -> Identity:
    if identity.role not in ("admin", "editor", "viewer"):
        raise HTTPException(status_code=403, detail="Viewer permission required")
    return identity
