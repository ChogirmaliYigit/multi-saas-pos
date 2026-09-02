from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    analytics,
    auth,
    catalog,
    employees,
    inventory,
    orders,
    platform,
    reports,
    shifts,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(catalog.router)
api_router.include_router(inventory.router)
api_router.include_router(orders.router)
api_router.include_router(shifts.router)
api_router.include_router(employees.router)
api_router.include_router(analytics.router)
api_router.include_router(reports.router)
api_router.include_router(platform.router)
