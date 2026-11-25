"""Main API router combining all sub-routers and health check."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from src.api import (
    agent_routes,
    booking_routes,
    business_routes,
    order_routes,
    review_routes,
    social_routes,
    storefront_routes,
    whatsapp_routes,
)
from src.database import get_db

api_router = APIRouter()


@api_router.get("/health", tags=["Health"])
async def health_check(db: AsyncSession = Depends(get_db)) -> dict:
    """Health check endpoint verifying API and database connectivity."""
    db_status = "connected"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db_status = f"error: {exc}"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "service": settings.app_name,
        "database": db_status,
        "timestamp": datetime.now(UTC).isoformat(),
    }


api_router.include_router(business_routes.router)
api_router.include_router(social_routes.router)
api_router.include_router(review_routes.router)
api_router.include_router(booking_routes.router)
api_router.include_router(order_routes.router)
api_router.include_router(agent_routes.router)
api_router.include_router(whatsapp_routes.router)
api_router.include_router(storefront_routes.router)
