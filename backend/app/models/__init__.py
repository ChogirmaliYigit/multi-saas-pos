"""Import every model here so Alembic autogenerate and Base.metadata see them."""

from app.db.base_class import Base
from app.models.audit import AuditLog, ReportJob
from app.models.catalog import (
    Category,
    Product,
    ProductBarcode,
    Supplier,
    TaxRate,
)
from app.models.enums import (
    BillingCycle,
    DiscountType,
    InvoiceStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ProductUnit,
    ReportFormat,
    ReportStatus,
    ReportType,
    ShiftStatus,
    StockMovementType,
    SubscriptionStatus,
    TenantStatus,
    UserRole,
)
from app.models.inventory import StockItem, StockMovement
from app.models.sales import (
    Customer,
    Order,
    OrderCounter,
    OrderItem,
    Payment,
    Refund,
    Shift,
)
from app.models.subscription import Plan, Subscription, SubscriptionInvoice
from app.models.tenant import Branch, Tenant
from app.models.user import PasswordResetToken, RefreshToken, User

__all__ = [
    "Base",
    "AuditLog",
    "ReportJob",
    "Category",
    "Product",
    "ProductBarcode",
    "Supplier",
    "TaxRate",
    "StockItem",
    "StockMovement",
    "Customer",
    "Order",
    "OrderCounter",
    "OrderItem",
    "Payment",
    "Refund",
    "Shift",
    "Plan",
    "Subscription",
    "SubscriptionInvoice",
    "Branch",
    "Tenant",
    "PasswordResetToken",
    "RefreshToken",
    "User",
    "BillingCycle",
    "DiscountType",
    "InvoiceStatus",
    "OrderStatus",
    "PaymentMethod",
    "PaymentStatus",
    "ProductUnit",
    "ReportFormat",
    "ReportStatus",
    "ReportType",
    "ShiftStatus",
    "StockMovementType",
    "SubscriptionStatus",
    "TenantStatus",
    "UserRole",
]
