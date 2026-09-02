"""Idempotent bootstrap data: subscription plans and the platform admin.

Run with:  python -m app.db.seed
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal, platform_scope
from app.db.tenant_filter import SKIP_TENANT_FILTER
from app.models.enums import UserRole
from app.models.subscription import Plan
from app.models.user import User

logger = logging.getLogger(__name__)

DEFAULT_PLANS = [
    {
        "code": "basic",
        "name": "Basic",
        "description": "One shop, one till.",
        "price_monthly": 19,
        "price_yearly": 190,
        "trial_days": 14,
        "max_branches": 1,
        "max_users": 3,
        "max_products": 500,
        "max_orders_per_month": 2000,
        "features": {"pdf_reports": False, "multi_branch": False, "api_access": False},
        "sort_order": 1,
    },
    {
        "code": "pro",
        "name": "Pro",
        "description": "Growing shops with a few branches.",
        "price_monthly": 49,
        "price_yearly": 490,
        "trial_days": 14,
        "max_branches": 5,
        "max_users": 20,
        "max_products": 10_000,
        "max_orders_per_month": 50_000,
        "features": {"pdf_reports": True, "multi_branch": True, "api_access": False},
        "sort_order": 2,
    },
    {
        "code": "enterprise",
        "name": "Enterprise",
        "description": "Unlimited everything.",
        "price_monthly": 149,
        "price_yearly": 1490,
        "trial_days": 30,
        "max_branches": None,
        "max_users": None,
        "max_products": None,
        "max_orders_per_month": None,
        "features": {"pdf_reports": True, "multi_branch": True, "api_access": True},
        "sort_order": 3,
    },
]


async def seed_plans() -> None:
    async with AsyncSessionLocal() as session:
        for spec in DEFAULT_PLANS:
            existing = await session.scalar(select(Plan).where(Plan.code == spec["code"]))
            if existing:
                continue
            session.add(Plan(**spec))
        await session.commit()
    logger.info("Plans seeded")


async def seed_super_admin() -> None:
    email = settings.SUPER_ADMIN_EMAIL
    password = settings.SUPER_ADMIN_PASSWORD
    if not email or not password:
        logger.warning("SUPER_ADMIN_EMAIL/SUPER_ADMIN_PASSWORD not set; skipping platform admin")
        return

    async with AsyncSessionLocal() as session, platform_scope(session):
        existing = await session.scalar(
            select(User)
            .where(User.email == email.lower())
            .execution_options(**{SKIP_TENANT_FILTER: True})
        )
        if existing:
            logger.info("Platform admin already present")
            return
        session.add(
            User(
                tenant_id=None,
                email=email.lower(),
                full_name="Platform Admin",
                hashed_password=hash_password(password),
                role=UserRole.SUPER_ADMIN,
                is_active=True,
            )
        )
        await session.commit()
    logger.info("Platform admin created")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await seed_plans()
    await seed_super_admin()


if __name__ == "__main__":
    asyncio.run(main())
