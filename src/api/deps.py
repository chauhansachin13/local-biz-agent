"""Shared async API helper dependencies."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.business import Business


async def get_business_or_404(db: AsyncSession, business_id: int) -> Business:
    """Fetch a Business by primary key or raise HTTP 404."""
    result = await db.execute(select(Business).where(Business.id == business_id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business with id={business_id} not found",
        )
    return business
