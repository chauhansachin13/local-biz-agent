"""Booking creation, listing, modification, cancellation, and availability routes."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.booking_agent import BookingAgent
from src.api.deps import get_business_or_404
from src.database import get_db
from src.models.api_schemas import AvailabilityResponse, BookingCreateRequest
from src.models.booking import (
    Booking,
    BookingResponse,
    BookingStatus,
    BookingUpdate,
)

router = APIRouter(prefix="/api/bookings", tags=["Bookings"])
booking_agent = BookingAgent()


@router.post(
    "/{business_id}/book",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_booking(
    business_id: int,
    payload: BookingCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> Booking:
    """Create a booking after validating slot availability."""
    business = await get_business_or_404(db, business_id)
    start_minutes = payload.booking_time.hour * 60 + payload.booking_time.minute

    if await booking_agent.has_conflict(
        db=db,
        business=business,
        target_date=payload.booking_date,
        start_minutes=start_minutes,
        duration_minutes=payload.duration_minutes,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Time slot {payload.booking_date} {payload.booking_time.strftime('%H:%M')} is fully booked.",
        )

    booking = Booking(
        business_id=business_id,
        status=BookingStatus.CONFIRMED,
        **payload.model_dump(),
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return booking


@router.get("/{business_id}/bookings", response_model=list[BookingResponse])
async def list_bookings(
    business_id: int,
    booking_status: BookingStatus | None = Query(default=None, alias="status"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[Booking]:
    """List bookings for a business with optional status and date filters."""
    await get_business_or_404(db, business_id)
    stmt = select(Booking).where(Booking.business_id == business_id)
    if booking_status is not None:
        stmt = stmt.where(Booking.status == booking_status)
    if date_from is not None:
        stmt = stmt.where(Booking.booking_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Booking.booking_date <= date_to)
    stmt = stmt.order_by(Booking.booking_date.asc(), Booking.booking_time.asc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.put("/{business_id}/bookings/{booking_id}", response_model=BookingResponse)
async def update_booking(
    business_id: int,
    booking_id: int,
    payload: BookingUpdate,
    db: AsyncSession = Depends(get_db),
) -> Booking:
    """Update an existing booking."""
    business = await get_business_or_404(db, business_id)
    stmt = select(Booking).where(
        Booking.id == booking_id,
        Booking.business_id == business_id,
    )
    booking = (await db.execute(stmt)).scalar_one_or_none()
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking {booking_id} not found for business {business_id}",
        )

    updates = payload.model_dump(exclude_unset=True)
    new_date = updates.get("booking_date", booking.booking_date)
    new_time = updates.get("booking_time", booking.booking_time)
    new_duration = updates.get("duration_minutes", booking.duration_minutes)
    new_status = updates.get("status", booking.status)

    if new_status != BookingStatus.CANCELLED and any(
        k in updates for k in ("booking_date", "booking_time", "duration_minutes")
    ):
        start_minutes = new_time.hour * 60 + new_time.minute
        if await booking_agent.has_conflict(
            db=db,
            business=business,
            target_date=new_date,
            start_minutes=start_minutes,
            duration_minutes=new_duration,
            exclude_booking_id=booking_id,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Time slot {new_date} {new_time.strftime('%H:%M')} is fully booked.",
            )

    for field, value in updates.items():
        setattr(booking, field, value)

    await db.commit()
    await db.refresh(booking)
    return booking


@router.delete("/{business_id}/bookings/{booking_id}", response_model=BookingResponse)
async def cancel_booking(
    business_id: int,
    booking_id: int,
    db: AsyncSession = Depends(get_db),
) -> Booking:
    """Cancel a booking by updating its status to CANCELLED."""
    await get_business_or_404(db, business_id)
    stmt = select(Booking).where(
        Booking.id == booking_id,
        Booking.business_id == business_id,
    )
    booking = (await db.execute(stmt)).scalar_one_or_none()
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking {booking_id} not found for business {business_id}",
        )

    booking.status = BookingStatus.CANCELLED
    await db.commit()
    await db.refresh(booking)
    return booking


@router.get("/{business_id}/availability", response_model=AvailabilityResponse)
async def check_availability(
    business_id: int,
    target_date: date = Query(default_factory=date.today, alias="date"),
    duration_minutes: int = Query(default=60, ge=15, le=480),
    db: AsyncSession = Depends(get_db),
) -> AvailabilityResponse:
    """Check available appointment/reservation slots for a date."""
    business = await get_business_or_404(db, business_id)
    avail = await booking_agent.get_availability(
        db=db,
        business=business,
        target_date=target_date,
        duration_minutes=duration_minutes,
    )
    return AvailabilityResponse(**avail)


@router.get("/{business_id}/calendar.ics")
async def export_bookings_ics(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Export active bookings as an RFC-5545 .ics calendar file for Google/Apple Calendar."""
    business = await get_business_or_404(db, business_id)
    stmt = (
        select(Booking)
        .where(
            Booking.business_id == business_id,
            Booking.status != BookingStatus.CANCELLED,
        )
        .order_by(Booking.booking_date.asc(), Booking.booking_time.asc())
    )
    bookings = list((await db.execute(stmt)).scalars().all())

    def _ics_escape(val: str) -> str:
        return (
            str(val or "")
            .replace("\\", "\\\\")
            .replace("\r\n", "\\n")
            .replace("\n", "\\n")
            .replace("\r", "")
            .replace(";", "\\;")
            .replace(",", "\\,")
        )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//BizPresence AI//{_ics_escape(business.name)}//EN",
        "CALSCALE:GREGORIAN",
    ]
    for b in bookings:
        start_dt = datetime.combine(b.booking_date, b.booking_time)
        end_dt = start_dt + timedelta(minutes=b.duration_minutes)
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:booking-{b.id}@bizpresence.local",
                f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}",
                f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}",
                f"SUMMARY:{_ics_escape(b.service)} - {_ics_escape(b.customer_name)}",
                f"DESCRIPTION:Phone: {_ics_escape(b.customer_phone)} | Status: {b.status.value}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    ics_body = "\r\n".join(lines) + "\r\n"
    return Response(
        content=ics_body,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="bookings_{business_id}.ics"'},
    )
