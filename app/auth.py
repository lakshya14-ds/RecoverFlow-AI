"""API key identities for local and small team deployments."""
from dataclasses import dataclass
import json
import secrets

from fastapi import HTTPException, Request
from app.config import settings


@dataclass(frozen=True)
class Identity:
    actor: str
    tenant_id: str
    role: str


def configured_keys() -> list[tuple[str, Identity]]:
    entries = []
    if settings.RECOVERFLOW_API_KEY:
        entries.append((settings.RECOVERFLOW_API_KEY, Identity("local_admin", "local", "admin")))
    if settings.APEX_API_KEY:
        entries.append((settings.APEX_API_KEY, Identity("local_admin", "local", "admin")))
    for key_mapping in (settings.RECOVERFLOW_API_KEYS_JSON, settings.APEX_API_KEYS_JSON):
        if not key_mapping:
            continue
        for item in json.loads(key_mapping):
            if item["role"] not in ("admin", "editor", "viewer"):
                raise ValueError("Invalid API key role")
            entries.append((item["key"], Identity(item["actor"], item["tenant_id"], item["role"])))
    return entries


def authenticate(key: str) -> Identity | None:
    for expected, identity in configured_keys():
        if secrets.compare_digest(key, expected):
            return identity
    return None


def get_identity(request: Request) -> Identity:
    identity = getattr(request.state, "identity", None)
    if not identity:
        raise HTTPException(status_code=401, detail="Authentication required")
    return identity
