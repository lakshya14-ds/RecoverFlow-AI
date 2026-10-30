"""
Authentication & Cryptographic Security Services
Provides PBKDF2-HMAC-SHA256 password hashing, API key generation, and token management.
Uses Python standard library hashlib & secrets with zero external binary dependencies.
"""
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple


PBKDF2_ALGORITHM = "sha256"
PBKDF2_ITERATIONS = 310_000  # OWASP recommendation for PBKDF2-HMAC-SHA256


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with a cryptographically secure random salt."""
    if not password:
        raise ValueError("Password cannot be empty")
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS
    )
    return f"pbkdf2_{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${salt}${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against PBKDF2-HMAC-SHA256 hashed string using constant-time comparison."""
    if not plain_password or not hashed_password:
        return False
    parts = hashed_password.split("$")
    if len(parts) != 4 or not parts[0].startswith("pbkdf2_"):
        return False
    
    algorithm = parts[0].replace("pbkdf2_", "")
    try:
        iterations = int(parts[1])
    except ValueError:
        return False
    salt = parts[2]
    expected_hex = parts[3]
    
    computed_key = hashlib.pbkdf2_hmac(
        algorithm,
        plain_password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations
    )
    return secrets.compare_digest(computed_key.hex(), expected_hex)


def generate_api_key(prefix: str = "rf") -> Tuple[str, str, str]:
    """
    Generate a secure random API key.
    Returns: (raw_key, key_prefix, key_hash)
    - raw_key: Returned to the user once upon creation (e.g. rf_live_3f4a...)
    - key_prefix: First 8-12 chars for display identification (e.g. rf_live_3f4a)
    - key_hash: SHA-256 hash stored in database
    """
    random_bytes = secrets.token_hex(24)
    raw_key = f"{prefix}_{random_bytes}"
    key_prefix = raw_key[:12]
    key_hash = hash_api_key(raw_key)
    return raw_key, key_prefix, key_hash


def hash_api_key(key: str) -> str:
    """Compute deterministic SHA-256 hash of an API key or token for lookup."""
    return hashlib.sha256(key.strip().encode("utf-8")).hexdigest()


def generate_session_token() -> Tuple[str, str]:
    """
    Generate a session token for web and API access.
    Returns: (raw_token, token_hash)
    """
    raw_token = f"rfs_{secrets.token_urlsafe(32)}"
    token_hash = hash_api_key(raw_token)
    return raw_token, token_hash


def generate_recovery_token():
    """
    Generate a single-use password recovery token for admin issuance.
    Returns: (raw_token, token_hash). The raw token is shown once only.
    """
    raw_token = f"rfr_{secrets.token_urlsafe(32)}"
    token_hash = hash_api_key(raw_token)
    return raw_token, token_hash
