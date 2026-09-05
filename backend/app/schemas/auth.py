from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import UserRole
from app.schemas.common import ORMModel

_PIN_RE = re.compile(r"^\d{4,6}$")


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until the access token expires


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    # Only needed when the request does not arrive on a tenant subdomain
    # (local dev, mobile apps hitting the bare API host).
    tenant_slug: str | None = Field(default=None, max_length=63)


class PinLoginRequest(BaseModel):
    """Mid-shift cashier switch on a terminal that is already authenticated."""

    user_id: uuid.UUID
    pin: str

    @field_validator("pin")
    @classmethod
    def _digits_only(cls, v: str) -> str:
        if not _PIN_RE.match(v):
            raise ValueError("PIN must be 4-6 digits")
        return v


class RefreshRequest(BaseModel):
    refresh_token: str


class SignupRequest(BaseModel):
    """Self-serve shop registration: creates the tenant, its first branch, the
    owner account and a trial subscription in one transaction."""

    shop_name: str = Field(min_length=2, max_length=160)
    slug: str = Field(min_length=3, max_length=63)
    owner_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    country_code: str = Field(default="US", min_length=2, max_length=2)
    timezone: str = "UTC"
    plan_code: str = "basic"

    @field_validator("slug")
    @classmethod
    def _valid_slug(cls, v: str) -> str:
        v = v.lower().strip()
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", v):
            raise ValueError("slug may contain only lowercase letters, digits and hyphens")
        if v in {"www", "api", "admin", "app", "static", "assets", "mail"}:
            raise ValueError("this slug is reserved")
        return v

    @field_validator("password")
    @classmethod
    def _strong_enough(cls, v: str) -> str:
        # Length is the property that actually matters; a full class-mix rule
        # pushes people toward "Passw0rd!". One weak-pattern check is enough.
        if v.lower() in {"password12", "12345678910", "qwertyuiop"}:
            raise ValueError("password is too common")
        return v


class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    # Needed when the request does not arrive on a tenant subdomain. Without
    # it the lookup falls to the platform namespace.
    tenant_slug: str | None = Field(default=None, max_length=63)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


class SetPinRequest(BaseModel):
    pin: str

    @field_validator("pin")
    @classmethod
    def _digits_only(cls, v: str) -> str:
        if not _PIN_RE.match(v):
            raise ValueError("PIN must be 4-6 digits")
        return v


class UserPublic(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    tenant_id: uuid.UUID | None
    branch_id: uuid.UUID | None
    phone: str | None
    avatar_url: str | None
    is_active: bool


class TerminalStaff(ORMModel):
    """Minimal profile for the PIN-login avatar picker. No email, so the
    terminal screen does not expose login identifiers to a shop floor."""

    id: uuid.UUID
    full_name: str
    role: UserRole
    avatar_url: str | None
    has_pin: bool


class SessionInfo(BaseModel):
    user: UserPublic
    tenant_slug: str | None
    permissions: list[str]
    # Every screen that shows a price needs this, including the terminal,
    # which a cashier reaches without permission to read the shop record.
    currency: str | None = None
