from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import UserRole
from app.schemas.common import ORMModel

_PIN_RE = re.compile(r"^\d{4,6}$")

# A shop owner may create staff, never another platform operator.
ASSIGNABLE_ROLES = {UserRole.OWNER, UserRole.MANAGER, UserRole.CASHIER}


class EmployeeIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    role: UserRole
    branch_id: uuid.UUID | None = None
    phone: str | None = Field(default=None, max_length=32)
    pin: str | None = None

    @field_validator("role")
    @classmethod
    def _no_platform_roles(cls, value: UserRole) -> UserRole:
        if value not in ASSIGNABLE_ROLES:
            raise ValueError("That role cannot be assigned from a shop account")
        return value

    @field_validator("pin")
    @classmethod
    def _digits(cls, value: str | None) -> str | None:
        if value and not _PIN_RE.match(value):
            raise ValueError("PIN must be 4-6 digits")
        return value


class EmployeeUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    role: UserRole | None = None
    branch_id: uuid.UUID | None = None
    phone: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None
    # {"deny": ["order.refund"]} -- deny always wins over role defaults.
    permission_overrides: dict | None = None

    @field_validator("role")
    @classmethod
    def _no_platform_roles(cls, value: UserRole | None) -> UserRole | None:
        if value is not None and value not in ASSIGNABLE_ROLES:
            raise ValueError("That role cannot be assigned from a shop account")
        return value


class ResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=10, max_length=128)


class EmployeeOut(ORMModel):
    id: uuid.UUID
    full_name: str
    email: str
    role: UserRole
    branch_id: uuid.UUID | None
    phone: str | None
    avatar_url: str | None
    is_active: bool
    has_pin: bool = False
    last_login_at: datetime | None
    created_at: datetime
    permissions: list[str] = []
