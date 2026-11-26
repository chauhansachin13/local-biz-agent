"""SQLAlchemy ORM models and Pydantic schemas for promo coupons, waitlist, FAQs, broadcasts, and ROI."""

from __future__ import annotations

import enum
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.database.db import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DiscountType(enum.StrEnum):
    """Discount calculation mode for coupon offers."""

    PERCENT = "percent"
    FIXED = "fixed"


class WaitlistStatus(enum.StrEnum):
    """Lifecycle status for a customer waitlist request."""

    WAITING = "waiting"
    NOTIFIED = "notified"
    BOOKED = "booked"
    CANCELLED = "cancelled"


class CouponOffer(Base):
    """Promotional coupon or discount code scoped to a business."""

    __tablename__ = "coupon_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    discount_type: Mapped[DiscountType] = mapped_column(
        Enum(DiscountType, native_enum=False),
        nullable=False,
        default=DiscountType.PERCENT,
    )
    discount_value: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    min_order_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    uses_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


class WaitlistEntry(Base):
    """Customer waitlist request automatically alerted when a slot opens."""

    __tablename__ = "waitlist_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(30), nullable=False)
    preferred_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    preferred_time: Mapped[str] = mapped_column(String(10), nullable=False, default="18:00")
    service: Mapped[str] = mapped_column(String(255), nullable=False, default="Reservation")
    status: Mapped[WaitlistStatus] = mapped_column(
        Enum(WaitlistStatus, native_enum=False),
        nullable=False,
        default=WaitlistStatus.WAITING,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class CouponCreateRequest(BaseModel):
    """Create a validated coupon code for storefront & WhatsApp checkout."""

    code: str = Field(..., min_length=2, max_length=40)
    title: str = Field(..., min_length=2, max_length=160)
    discount_type: DiscountType = DiscountType.PERCENT
    discount_value: float = Field(..., gt=0.0)
    min_order_amount: float = Field(default=0.0, ge=0.0)
    max_uses: int = Field(default=100, ge=1, le=100000)
    valid_until: date | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def _validate_discount_cap(self) -> CouponCreateRequest:
        self.code = self.code.strip().upper().replace(" ", "")
        if not self.code.isalnum() and not all(c.isalnum() or c in "-_" for c in self.code):
            raise ValueError("Coupon code may only contain letters, digits, '-' or '_'.")
        if self.discount_type == DiscountType.PERCENT and self.discount_value > 100.0:
            raise ValueError("Percentage discount_value cannot exceed 100.")
        return self


class CouponUpdateRequest(BaseModel):
    """Activate, deactivate, or extend a coupon."""

    is_active: bool | None = None
    max_uses: int | None = Field(default=None, ge=1, le=100000)
    valid_until: date | None = None


class CouponResponse(BaseModel):
    """Coupon record API response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    code: str
    title: str
    discount_type: DiscountType
    discount_value: float
    min_order_amount: float
    max_uses: int
    uses_count: int
    valid_until: date | None = None
    is_active: bool
    created_at: datetime


class CouponValidateRequest(BaseModel):
    """Preview/validate a promo code against a cart subtotal."""

    code: str = Field(..., min_length=1, max_length=40)
    subtotal: float = Field(..., ge=0.0)


class CouponValidateResponse(BaseModel):
    """Structured coupon validation calculation result."""

    valid: bool
    code: str
    subtotal: float
    discount_amount: float
    final_total: float
    reason: str
    coupon: CouponResponse | None = None


class WaitlistCreateRequest(BaseModel):
    """Add a customer onto the booking waitlist."""

    customer_name: str = Field(..., min_length=1, max_length=255)
    customer_phone: str = Field(..., min_length=5, max_length=30)
    preferred_date: date
    preferred_time: str = Field(default="18:00", pattern=r"^\d{2}:\d{2}$")
    service: str = Field(default="Reservation", min_length=1, max_length=255)
    notes: str | None = None


class WaitlistStatusUpdate(BaseModel):
    """Update status of a waitlist entry."""

    status: WaitlistStatus


class WaitlistResponse(BaseModel):
    """Customer waitlist API response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    customer_name: str
    customer_phone: str
    preferred_date: date
    preferred_time: str
    service: str
    status: WaitlistStatus
    notes: str | None = None
    created_at: datetime


class FaqItemSchema(BaseModel):
    """Question/answer entry for grounded concierge responses."""

    q: str = Field(..., min_length=2, max_length=300)
    a: str = Field(..., min_length=2, max_length=1000)


class FaqListUpdateRequest(BaseModel):
    """Replace the business FAQ knowledge base."""

    faqs: list[FaqItemSchema] = Field(default_factory=list)


class BroadcastRequest(BaseModel):
    """Segmented WhatsApp/SMS customer broadcast request."""

    segment: str = Field(default="All", pattern="^(All|VIP|Regular|New)$")
    topic: str = Field(..., min_length=3, max_length=300)
    promo_code: str | None = Field(default=None, max_length=40)
    auto_execute: bool = False


class BroadcastResponse(BaseModel):
    """Result of dispatching or queueing a segmented broadcast."""

    business_id: int
    segment: str
    targeted_customers: int
    status: str
    sample_message: str
    approval_action_id: int | None = None


class TranslateRequest(BaseModel):
    """Request to localize marketing or support text into a target neighborhood language."""

    text: str = Field(..., min_length=1, max_length=2000)
    target_language: str = Field(..., min_length=2, max_length=40)


class TranslateResponse(BaseModel):
    """Translated text response."""

    business_id: int
    target_language: str
    original_text: str
    translated_text: str
    notes: str
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
