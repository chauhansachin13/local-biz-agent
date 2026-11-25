from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.db import Base

if TYPE_CHECKING:
    from src.models.business import Business


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ResponseStatus(str, enum.Enum):
    """Status of the business response to a customer review."""

    PENDING = "pending"
    RESPONDED = "responded"
    FLAGGED = "flagged"


class Sentiment(str, enum.Enum):
    """Detected sentiment of a customer review."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class Review(Base):
    """SQLAlchemy ORM model representing a customer review."""

    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_review_rating_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    reviewer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    review_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_status: Mapped[ResponseStatus] = mapped_column(
        Enum(ResponseStatus, native_enum=False),
        nullable=False,
        default=ResponseStatus.PENDING,
        index=True,
    )
    sentiment: Mapped[Optional[Sentiment]] = mapped_column(
        Enum(Sentiment, native_enum=False), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    business: Mapped[Business] = relationship("Business", back_populates="reviews")


class ReviewBase(BaseModel):
    """Shared Pydantic fields for Review schemas."""

    business_id: int
    platform: str = Field(..., min_length=1, max_length=50)
    reviewer_name: str = Field(..., min_length=1, max_length=255)
    rating: int = Field(..., ge=1, le=5)
    review_text: Optional[str] = None
    response_text: Optional[str] = None
    response_status: ResponseStatus = ResponseStatus.PENDING
    sentiment: Optional[Sentiment] = None
    responded_at: Optional[datetime] = None


class ReviewCreate(ReviewBase):
    """Schema for creating a new review."""


class ReviewUpdate(BaseModel):
    """Schema for partially updating a review or its response."""

    platform: Optional[str] = Field(default=None, min_length=1, max_length=50)
    reviewer_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    review_text: Optional[str] = None
    response_text: Optional[str] = None
    response_status: Optional[ResponseStatus] = None
    sentiment: Optional[Sentiment] = None
    responded_at: Optional[datetime] = None


class ReviewResponse(ReviewBase):
    """Schema returned when reading a review."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
