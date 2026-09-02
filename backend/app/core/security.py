from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings

TokenType = Literal["access", "refresh"]

# Argon2id with the OWASP-recommended baseline. Chosen over bcrypt because it
# has no 72-byte truncation surprise and is memory-hard.
_hasher = PasswordHasher(time_cost=2, memory_cost=64 * 1024, parallelism=2)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        _hasher.verify(hashed, password)
        return True
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def password_needs_rehash(hashed: str) -> bool:
    """True when the stored hash used weaker parameters than we use today."""
    try:
        return _hasher.check_needs_rehash(hashed)
    except (InvalidHashError, ValueError):
        return True


def hash_pin(pin: str) -> str:
    return _hasher.hash(pin)


def verify_pin(pin: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    return verify_password(pin, hashed)


def create_token(
    *,
    subject: uuid.UUID,
    token_type: TokenType,
    tenant_id: uuid.UUID | None,
    role: str,
    branch_id: uuid.UUID | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, str, datetime]:
    """Returns (encoded_jwt, jti, expires_at).

    `tid` is baked into the token. It is the only source of tenant identity the
    API trusts -- a client cannot ask for another shop's data by changing a
    header, a body field, or a subdomain.
    """
    now = datetime.now(UTC)
    if expires_delta is None:
        expires_delta = (
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            if token_type == "access"
            else timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        )
    expires_at = now + expires_delta
    jti = secrets.token_urlsafe(16)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "tid": str(tenant_id) if tenant_id else None,
        "role": role,
        "bid": str(branch_id) if branch_id else None,
        "typ": token_type,
        "jti": jti,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    encoded = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded, jti, expires_at


def decode_token(token: str, *, expected_type: TokenType | None = None) -> dict[str, Any]:
    """Raises jwt.PyJWTError on anything wrong: bad signature, expiry, or a
    refresh token presented where an access token belongs."""
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["exp", "iat", "sub", "typ", "jti"]},
    )
    if expected_type is not None and payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError(f"expected a {expected_type} token, got {payload.get('typ')!r}")
    return payload


def hash_refresh_token(token: str) -> str:
    """Refresh tokens are stored as digests only. A database dump must not
    hand an attacker a set of live sessions."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_secret(length: int = 32) -> str:
    return secrets.token_urlsafe(length)
