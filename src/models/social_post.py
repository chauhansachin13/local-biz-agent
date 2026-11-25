from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.db import Base

if TYPE_CHECKING:
    from src.models.business import Business


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SocialPlatform(enum.StrEnum):
    """Supported social media platforms."""

    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    TWITTER = "twitter"
    GOOGLE = "google"


class PostStatus(enum.StrEnum):
    """Lifecycle status of a social post."""

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"


class SocialPost(Base):
    """SQLAlchemy ORM model representing a business social media post."""

    __tablename__ = "social_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform: Mapped[SocialPlatform] = mapped_column(
        Enum(SocialPlatform, native_enum=False), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[PostStatus] = mapped_column(
        Enum(PostStatus, native_enum=False),
        nullable=False,
        default=PostStatus.DRAFT,
        index=True,
    )
    engagement_likes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    engagement_shares: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    engagement_comments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )

    business: Mapped[Business] = relationship("Business", back_populates="social_posts")


class SocialPostBase(BaseModel):
    """Shared Pydantic fields for SocialPost schemas."""

    business_id: int
    platform: SocialPlatform
    content: str = Field(..., min_length=1)
    image_url: str | None = Field(default=None, max_length=1000)
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    status: PostStatus = PostStatus.DRAFT
    engagement_likes: int = Field(default=0, ge=0)
    engagement_shares: int = Field(default=0, ge=0)
    engagement_comments: int = Field(default=0, ge=0)


class SocialPostCreate(SocialPostBase):
    """Schema for creating a new social post."""


class SocialPostUpdate(BaseModel):
    """Schema for partially updating a social post."""

    platform: SocialPlatform | None = None
    content: str | None = Field(default=None, min_length=1)
    image_url: str | None = Field(default=None, max_length=1000)
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    status: PostStatus | None = None
    engagement_likes: int | None = Field(default=None, ge=0)
    engagement_shares: int | None = Field(default=None, ge=0)
    engagement_comments: int | None = Field(default=None, ge=0)


class SocialPostResponse(SocialPostBase):
    """Schema returned when reading a social post."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
