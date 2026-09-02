from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentTenant, CurrentUser, DbSession, require, resolve_branch_id
from app.core import quotas
from app.core.permissions import Permission
from app.schemas.analytics import (
    DashboardSummary,
    LowStockItem,
    PaymentBreakdown,
    RevenuePoint,
    SalesByHour,
    TopProduct,
)
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get(
    "/dashboard",
    response_model=DashboardSummary,
    dependencies=[Depends(require(Permission.REPORT_READ))],
)
async def dashboard(
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
    branch_id: uuid.UUID | None = None,
) -> DashboardSummary:
    return await analytics_service.dashboard_summary(db, tenant, resolve_branch_id(user, branch_id))


@router.get(
    "/revenue",
    response_model=list[RevenuePoint],
    dependencies=[Depends(require(Permission.REPORT_READ))],
)
async def revenue(
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
    days: int = Query(30, ge=1, le=365),
    branch_id: uuid.UUID | None = None,
) -> list[RevenuePoint]:
    return await analytics_service.revenue_series(
        db, tenant, days=days, branch_id=resolve_branch_id(user, branch_id)
    )


@router.get(
    "/top-products",
    response_model=list[TopProduct],
    dependencies=[Depends(require(Permission.REPORT_READ))],
)
async def top_products(
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    branch_id: uuid.UUID | None = None,
) -> list[TopProduct]:
    return await analytics_service.top_products(
        db, tenant, days=days, limit=limit, branch_id=resolve_branch_id(user, branch_id)
    )


@router.get(
    "/low-stock",
    response_model=list[LowStockItem],
    dependencies=[Depends(require(Permission.STOCK_READ))],
)
async def low_stock(
    db: DbSession,
    user: CurrentUser,
    branch_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> list[LowStockItem]:
    return await analytics_service.low_stock_items(
        db, branch_id=resolve_branch_id(user, branch_id), limit=limit
    )


@router.get(
    "/payments",
    response_model=list[PaymentBreakdown],
    dependencies=[Depends(require(Permission.REPORT_READ))],
)
async def payments(
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
    days: int = Query(30, ge=1, le=365),
    branch_id: uuid.UUID | None = None,
) -> list[PaymentBreakdown]:
    return await analytics_service.payment_breakdown(
        db, tenant, days=days, branch_id=resolve_branch_id(user, branch_id)
    )


@router.get(
    "/hourly",
    response_model=list[SalesByHour],
    dependencies=[Depends(require(Permission.REPORT_READ))],
)
async def hourly(
    db: DbSession,
    tenant: CurrentTenant,
    user: CurrentUser,
    days: int = Query(7, ge=1, le=90),
    branch_id: uuid.UUID | None = None,
) -> list[SalesByHour]:
    return await analytics_service.sales_by_hour(
        db, tenant, days=days, branch_id=resolve_branch_id(user, branch_id)
    )


@router.get(
    "/usage",
    dependencies=[Depends(require(Permission.BILLING_READ))],
)
async def plan_usage(db: DbSession, tenant: CurrentTenant) -> dict:
    """Usage against plan limits, shown before a ceiling is hit rather than at
    the moment someone needs to add a till."""
    return await quotas.usage_summary(db, tenant.id)
