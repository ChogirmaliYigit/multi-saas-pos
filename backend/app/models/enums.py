from __future__ import annotations

import enum


class TenantStatus(str, enum.Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"  # blocked by the SaaS owner or non-payment
    CANCELLED = "cancelled"


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"  # SaaS owner, tenant_id IS NULL
    OWNER = "owner"  # shop owner, full access to one tenant
    MANAGER = "manager"  # inventory + reports, no billing/user deletion
    CASHIER = "cashier"  # POS terminal only


class BillingCycle(str, enum.Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class SubscriptionStatus(str, enum.Enum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    EXPIRED = "expired"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    VOID = "void"
    UNCOLLECTIBLE = "uncollectible"


class ProductUnit(str, enum.Enum):
    PIECE = "piece"
    KG = "kg"
    GRAM = "gram"
    LITER = "liter"
    METER = "meter"
    PACK = "pack"
    BOX = "box"


class StockMovementType(str, enum.Enum):
    INITIAL = "initial"
    PURCHASE = "purchase"
    SALE = "sale"
    RETURN = "return"
    ADJUSTMENT = "adjustment"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    WASTE = "waste"


class OrderStatus(str, enum.Enum):
    DRAFT = "draft"  # parked / held cart
    COMPLETED = "completed"
    PARTIALLY_REFUNDED = "partially_refunded"
    REFUNDED = "refunded"
    VOIDED = "voided"


class DiscountType(str, enum.Enum):
    NONE = "none"
    PERCENT = "percent"
    FIXED = "fixed"


class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    CARD = "card"
    MOBILE = "mobile"
    BANK_TRANSFER = "bank_transfer"
    STORE_CREDIT = "store_credit"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"


class ShiftStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"


class ReportType(str, enum.Enum):
    SALES_SUMMARY = "sales_summary"
    SALES_DETAILED = "sales_detailed"
    TAX = "tax"
    INVENTORY = "inventory"
    EMPLOYEE_PERFORMANCE = "employee_performance"


class ReportStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ReportFormat(str, enum.Enum):
    CSV = "csv"
    PDF = "pdf"
    XLSX = "xlsx"


class PaymentProvider(str, enum.Enum):
    PAYME = "payme"
    CLICK = "click"
    MANUAL = "manual"


class TransactionState(str, enum.Enum):
    """Deliberately provider-neutral.

    Payme and Click describe the same lifecycle with different vocabularies
    and different integer codes; each adapter maps to and from these so the
    billing domain never learns a provider's dialect.
    """

    CREATED = "created"  # provider holds it, money not moved
    PERFORMED = "performed"  # paid
    CANCELLED = "cancelled"  # cancelled before payment
    REFUNDED = "refunded"  # cancelled after payment
