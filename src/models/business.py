from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.db import Base

if TYPE_CHECKING:
    from src.models.booking import Booking
    from src.models.review import Review
    from src.models.social_post import SocialPost


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Business(Base):
    """SQLAlchemy ORM model representing a local business profile."""

    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    state: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    zip_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    google_business_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True
    )
    logo_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    cover_image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    operating_hours: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )

    social_posts: Mapped[list[SocialPost]] = relationship(
        "SocialPost", back_populates="business", cascade="all, delete-orphan"
    )
    reviews: Mapped[list[Review]] = relationship(
        "Review", back_populates="business", cascade="all, delete-orphan"
    )
    bookings: Mapped[list[Booking]] = relationship(
        "Booking", back_populates="business", cascade="all, delete-orphan"
    )


class BusinessBase(BaseModel):
    """Shared Pydantic fields for Business schemas."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: str = Field(..., min_length=1, max_length=120)
    address: Optional[str] = Field(default=None, max_length=500)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, max_length=120)
    zip_code: Optional[str] = Field(default=None, max_length=20)
    phone: Optional[str] = Field(default=None, max_length=30)
    email: Optional[str] = Field(default=None, max_length=255)
    website: Optional[str] = Field(default=None, max_length=500)
    google_business_id: Optional[str] = Field(default=None, max_length=255)
    logo_url: Optional[str] = Field(default=None, max_length=1000)
    cover_image_url: Optional[str] = Field(default=None, max_length=1000)
    operating_hours: Optional[dict[str, Any]] = None


class BusinessCreate(BusinessBase):
    """Schema for creating a new business."""


class BusinessUpdate(BaseModel):
    """Schema for partially updating an existing business."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(default=None, min_length=1, max_length=120)
    address: Optional[str] = Field(default=None, max_length=500)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, max_length=120)
    zip_code: Optional[str] = Field(default=None, max_length=20)
    phone: Optional[str] = Field(default=None, max_length=30)
    email: Optional[str] = Field(default=None, max_length=255)
    website: Optional[str] = Field(default=None, max_length=500)
    google_business_id: Optional[str] = Field(default=None, max_length=255)
    logo_url: Optional[str] = Field(default=None, max_length=1000)
    cover_image_url: Optional[str] = Field(default=None, max_length=1000)
    operating_hours: Optional[dict[str, Any]] = None


class BusinessResponse(BusinessBase):
    """Schema returned when reading a business."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
