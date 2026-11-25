"""Online customer orders and service request routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_business_or_404
from src.database import get_db
from src.models.agent_models import (
    OrderCreateRequest,
    OrderRequest,
    OrderResponse,
    OrderStatus,
    OrderStatusUpdate,
)

router = APIRouter(prefix="/api/orders", tags=["Online Orders"])


@router.post(
    "/{business_id}/order",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    business_id: int,
    payload: OrderCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> OrderRequest:
    """Create an online pickup, delivery, or dine-in order for a local business."""
    await get_business_or_404(db, business_id)
    items_dicts = [item.model_dump() for item in payload.items]
    total = round(sum(item.price * item.quantity for item in payload.items), 2)

    order = OrderRequest(
        business_id=business_id,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        customer_email=payload.customer_email,
        items=items_dicts,
        total_amount=total,
        fulfillment_type=payload.fulfillment_type,
        status=OrderStatus.NEW,
        notes=payload.notes,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


@router.get("/{business_id}/orders", response_model=list[OrderResponse])
async def list_orders(
    business_id: int,
    order_status: OrderStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[OrderRequest]:
    """List online orders for a business with optional status filter."""
    await get_business_or_404(db, business_id)
    stmt = select(OrderRequest).where(OrderRequest.business_id == business_id)
    if order_status is not None:
        stmt = stmt.where(OrderRequest.status == order_status)
    stmt = stmt.order_by(OrderRequest.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


@router.put("/{business_id}/orders/{order_id}", response_model=OrderResponse)
async def update_order_status(
    business_id: int,
    order_id: int,
    payload: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> OrderRequest:
    """Update the status of an online customer order."""
    await get_business_or_404(db, business_id)
    stmt = select(OrderRequest).where(
        OrderRequest.id == order_id,
        OrderRequest.business_id == business_id,
    )
    order = (await db.execute(stmt)).scalar_one_or_none()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found for business {business_id}",
        )
    order.status = payload.status
    if payload.notes is not None:
        order.notes = payload.notes
    await db.commit()
    await db.refresh(order)
    return order
