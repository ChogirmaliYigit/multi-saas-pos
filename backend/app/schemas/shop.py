from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import TenantStatus
from app.schemas.common import ORMModel


class BranchIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    code: str = Field(min_length=1, max_length=32)
    address: str | None = None
    phone: str | None = Field(default=None, max_length=32)
    timezone: str | None = Field(default=None, max_length=64)
    is_default: bool = False

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str) -> str:
        # The code prefixes every receipt number, so it is normalised once
        # here rather than appearing as both MAIN and main on paper.
        return value.strip().upper()


class BranchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    address: str | None = None
    phone: str | None = Field(default=None, max_length=32)
    timezone: str | None = Field(default=None, max_length=64)
    is_default: bool | None = None
    is_active: bool | None = None
    # `code` is absent on purpose: it is baked into every receipt number this
    # branch has ever issued, and changing it would break that series.


class BranchOut(ORMModel):
    id: uuid.UUID
    name: str
    code: str
    address: str | None
    phone: str | None
    timezone: str | None
    is_default: bool
    is_active: bool
    created_at: datetime
    staff_count: int = 0
    product_count: int = 0
    orders_last_30_days: int = 0


class ShopSettings(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    legal_name: str | None
    tax_number: str | None
    email: str
    phone: str | None
    address: str | None
    country_code: str
    currency: str
    timezone: str
    locale: str
    logo_url: str | None
    receipt_header: str | None
    receipt_footer: str | None
    status: TenantStatus
    settings: dict


class ShopSettingsUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    legal_name: str | None = Field(default=None, max_length=200)
    tax_number: str | None = Field(default=None, max_length=64)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    address: str | None = None
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=10)
    logo_url: str | None = Field(default=None, max_length=500)
    receipt_header: str | None = None
    receipt_footer: str | None = None
    # Free-form switches: allow_negative_stock, cash_rounding, receipt_width_mm.
    settings: dict | None = None

    # `currency` and `slug` are absent. Currency is stamped on every past
    # order and changing it would silently re-denominate a shop's history;
    # slug is the subdomain and the login identifier. Both are operator
    # actions, not self-service ones.


class TaxRateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    rate: Decimal | None = Field(default=None, ge=0, le=1)
    is_inclusive: bool | None = None
    is_default: bool | None = None
    is_active: bool | None = None


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    avatar_url: str | None = Field(default=None, max_length=500)
