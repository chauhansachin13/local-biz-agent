from __future__ import annotations

import enum
from datetime import UTC, date, datetime, time
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.db import Base

if TYPE_CHECKING:
    from src.models.business import Business


def _utc_now() -> datetime:
    return datetime.now(UTC)


class BookingStatus(enum.StrEnum):
    """Lifecycle status of a customer booking."""

    CONFIRMED = "confirmed"
    PENDING = "pending"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class Booking(Base):
    """SQLAlchemy ORM model representing a customer service booking."""

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(30), nullable=False)
    service: Mapped[str] = mapped_column(String(255), nullable=False)
    booking_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    booking_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, native_enum=False),
        nullable=False,
        default=BookingStatus.PENDING,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )

    business: Mapped[Business] = relationship("Business", back_populates="bookings")


class BookingBase(BaseModel):
    """Shared Pydantic fields for Booking schemas."""

    business_id: int
    customer_name: str = Field(..., min_length=1, max_length=255)
    customer_email: str = Field(..., min_length=3, max_length=255)
    customer_phone: str = Field(..., min_length=5, max_length=30)
    service: str = Field(..., min_length=1, max_length=255)
    booking_date: date
    booking_time: time
    duration_minutes: int = Field(default=30, ge=5, le=1440)
    status: BookingStatus = BookingStatus.PENDING
    notes: str | None = None


class BookingCreate(BookingBase):
    """Schema for creating a new booking."""


class BookingUpdate(BaseModel):
    """Schema for partially updating an existing booking."""

    customer_name: str | None = Field(default=None, min_length=1, max_length=255)
    customer_email: str | None = Field(default=None, min_length=3, max_length=255)
    customer_phone: str | None = Field(default=None, min_length=5, max_length=30)
    service: str | None = Field(default=None, min_length=1, max_length=255)
    booking_date: date | None = None
    booking_time: time | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=1440)
    status: BookingStatus | None = None
    notes: str | None = None


class BookingResponse(BookingBase):
    """Schema returned when reading a booking."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
