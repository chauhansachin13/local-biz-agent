"""Booking availability and conflict-checking helper agent (async SQLAlchemy)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.booking import Booking, BookingStatus
from src.models.business import Business


def _to_minutes(hhmm: str) -> int:
    parts = hhmm.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


class BookingAgent:
    """Computes open booking slots and checks for scheduling conflicts."""

    def _max_concurrent(self, business: Business) -> int:
        cat = (business.category or "").lower()
        return 4 if any(k in cat for k in ("restaurant", "cafe", "dining")) else 1

    def _day_hours(self, business: Business, target_date: date) -> dict[str, Any]:
        day_name = target_date.strftime("%A").lower()
        hours_map = business.operating_hours or {}
        cfg = hours_map.get(day_name)
        if isinstance(cfg, dict):
            return cfg
        return {"open": "09:00", "close": "18:00", "closed": False}

    async def get_availability(
        self,
        db: AsyncSession,
        business: Business,
        target_date: date,
        duration_minutes: int = 60,
        slot_step_minutes: int = 30,
    ) -> dict[str, Any]:
        """Compute time slots for target_date respecting operating_hours and existing bookings."""
        day_name = target_date.strftime("%A").lower()
        day_cfg = self._day_hours(business, target_date)

        if day_cfg.get("closed"):
            return {
                "business_id": business.id,
                "date": target_date.isoformat(),
                "day_of_week": day_name,
                "is_open": False,
                "open_time": None,
                "close_time": None,
                "slots": [],
                "available_count": 0,
            }

        open_str = day_cfg.get("open", "09:00")
        close_str = day_cfg.get("close", "18:00")
        open_min = _to_minutes(open_str)
        close_min = _to_minutes(close_str)

        stmt = select(Booking).where(
            Booking.business_id == business.id,
            Booking.booking_date == target_date,
            Booking.status != BookingStatus.CANCELLED,
        )
        result = await db.execute(stmt)
        existing = result.scalars().all()

        busy_intervals = [
            (
                b.booking_time.hour * 60 + b.booking_time.minute,
                b.booking_time.hour * 60 + b.booking_time.minute + b.duration_minutes,
            )
            for b in existing
        ]
        max_concurrent = self._max_concurrent(business)

        slots: list[dict[str, Any]] = []
        cursor = open_min
        while cursor + duration_minutes <= close_min:
            slot_end = cursor + duration_minutes
            overlaps = sum(
                1 for b_start, b_end in busy_intervals if cursor < b_end and slot_end > b_start
            )
            slots.append(
                {
                    "start_time": _to_hhmm(cursor),
                    "end_time": _to_hhmm(slot_end),
                    "available": overlaps < max_concurrent,
                }
            )
            cursor += slot_step_minutes

        return {
            "business_id": business.id,
            "date": target_date.isoformat(),
            "day_of_week": day_name,
            "is_open": True,
            "open_time": open_str,
            "close_time": close_str,
            "slots": slots,
            "available_count": sum(1 for s in slots if s["available"]),
        }

    async def has_conflict(
        self,
        db: AsyncSession,
        business: Business,
        target_date: date,
        start_minutes: int,
        duration_minutes: int,
        exclude_booking_id: int | None = None,
    ) -> bool:
        """Return True if the requested slot exceeds concurrent booking capacity."""
        req_end = start_minutes + duration_minutes
        stmt = select(Booking).where(
            Booking.business_id == business.id,
            Booking.booking_date == target_date,
            Booking.status != BookingStatus.CANCELLED,
        )
        if exclude_booking_id is not None:
            stmt = stmt.where(Booking.id != exclude_booking_id)

        result = await db.execute(stmt)
        existing = result.scalars().all()
        overlaps = sum(
            1
            for b in existing
            if start_minutes
            < (b.booking_time.hour * 60 + b.booking_time.minute + b.duration_minutes)
            and req_end > (b.booking_time.hour * 60 + b.booking_time.minute)
        )
        return overlaps >= self._max_concurrent(business)

    async def next_available_summary(self, db: AsyncSession, business: Business) -> str:
        """Summarize the earliest open booking slots over the next 3 days."""
        today = date.today()
        for offset in range(3):
            d = today + timedelta(days=offset)
            avail = await self.get_availability(db, business, d)
            open_slots = [s["start_time"] for s in avail["slots"] if s["available"]]
            if open_slots:
                label = "today" if offset == 0 else ("tomorrow" if offset == 1 else d.isoformat())
                return f"{label} ({', '.join(open_slots[:5])})"
        return "no open slots in the next 3 days"
