"""Loyalty Points, Gift Cards, NPS Surveys, and Email Campaign ORM models."""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database.db import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LoyaltyTier(enum.StrEnum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class LoyaltyTransactionType(enum.StrEnum):
    EARN = "earn"
    REDEEM = "redeem"
    EXPIRE = "expire"
    BONUS = "bonus"
    ADJUSTMENT = "adjustment"


class GiftCardStatus(enum.StrEnum):
    ACTIVE = "active"
    REDEEMED = "redeemed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class NPSSurveyStatus(enum.StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    ARCHIVED = "archived"


class EmailCampaignStatus(enum.StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENT = "sent"
    CANCELLED = "cancelled"


class EmailCampaignType(enum.StrEnum):
    NEWSLETTER = "newsletter"
    PROMOTIONAL = "promotional"
    TRANSACTIONAL = "transactional"
    REENGAGEMENT = "reengagement"
    ANNOUNCEMENT = "announcement"


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


class LoyaltyAccount(Base):
    """Customer loyalty points account."""

    __tablename__ = "loyalty_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    points_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lifetime_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tier: Mapped[LoyaltyTier] = mapped_column(
        Enum(LoyaltyTier, native_enum=False),
        nullable=False,
        default=LoyaltyTier.BRONZE,
    )
    tier_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


class LoyaltyTransaction(Base):
    """Individual point earn/redeem transaction."""

    __tablename__ = "loyalty_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("loyalty_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    business_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    transaction_type: Mapped[LoyaltyTransactionType] = mapped_column(
        Enum(LoyaltyTransactionType, native_enum=False), nullable=False
    )
    points: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # positive = earn, negative = redeem
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(255), nullable=True)  # order/booking ID
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


class GiftCard(Base):
    """Digital gift card issued by a business."""

    __tablename__ = "gift_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    initial_amount: Mapped[float] = mapped_column(Float, nullable=False)
    remaining_amount: Mapped[float] = mapped_column(Float, nullable=False)
    recipient_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[GiftCardStatus] = mapped_column(
        Enum(GiftCardStatus, native_enum=False),
        nullable=False,
        default=GiftCardStatus.ACTIVE,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


class NPSSurvey(Base):
    """Net Promoter Score survey response."""

    __tablename__ = "nps_surveys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-10
    category: Mapped[str] = mapped_column(String(20), nullable=False)  # promoter/passive/detractor
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[NPSSurveyStatus] = mapped_column(
        Enum(NPSSurveyStatus, native_enum=False),
        nullable=False,
        default=NPSSurveyStatus.SUBMITTED,
    )
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)  # email/widget/sms
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


class EmailCampaign(Base):
    """Email marketing campaign."""

    __tablename__ = "email_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    campaign_type: Mapped[EmailCampaignType] = mapped_column(
        Enum(EmailCampaignType, native_enum=False),
        nullable=False,
        default=EmailCampaignType.NEWSLETTER,
    )
    status: Mapped[EmailCampaignStatus] = mapped_column(
        Enum(EmailCampaignStatus, native_enum=False),
        nullable=False,
        default=EmailCampaignStatus.DRAFT,
    )
    target_segment: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # all/loyal/new/vip
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    click_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unsubscribe_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


class ContentCalendarEntry(Base):
    """AI-generated content calendar entry for a business."""

    __tablename__ = "content_calendar"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)  # post/story/email/offer
    platform: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # instagram/facebook/email/all
    draft_content: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    scheduled_date: Mapped[str | None] = mapped_column(String(20), nullable=True)  # ISO date string
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="planned"
    )  # planned/approved/published
    ai_confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    occasion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class LoyaltyAccountCreate(BaseModel):
    customer_email: EmailStr
    customer_name: str = Field(..., min_length=1, max_length=255)


class LoyaltyEarnRequest(BaseModel):
    customer_email: EmailStr
    points: int = Field(..., ge=1, le=10000)
    description: str | None = Field(default=None, max_length=500)
    reference_id: str | None = Field(default=None, max_length=255)


class LoyaltyRedeemRequest(BaseModel):
    customer_email: EmailStr
    points: int = Field(..., ge=1, le=50000)
    description: str | None = Field(default=None, max_length=500)


class LoyaltyAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    customer_email: str
    customer_name: str
    points_balance: int
    lifetime_points: int
    tier: LoyaltyTier
    is_active: bool
    created_at: datetime


class GiftCardCreate(BaseModel):
    amount: float = Field(..., gt=0, le=10000)
    recipient_email: EmailStr | None = None
    recipient_name: str | None = Field(default=None, max_length=255)
    sender_email: EmailStr | None = None
    message: str | None = Field(default=None, max_length=1000)
    expires_days: int | None = Field(default=365, ge=1, le=1825)


class GiftCardRedeemRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=32)
    amount: float = Field(..., gt=0)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if len(cleaned) < 4:
            msg = "Gift card code must be at least 4 characters"
            raise ValueError(msg)
        return cleaned


class GiftCardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    initial_amount: float
    remaining_amount: float
    recipient_email: str | None
    recipient_name: str | None
    status: GiftCardStatus
    expires_at: datetime | None
    created_at: datetime


class NPSSurveyCreate(BaseModel):
    customer_email: EmailStr
    customer_name: str | None = Field(default=None, max_length=255)
    score: int = Field(..., ge=0, le=10)
    feedback: str | None = Field(default=None, max_length=2000)
    source: str | None = Field(default="widget", max_length=50)

    @field_validator("score")
    @classmethod
    def validate_score(cls, v: int) -> int:
        if not 0 <= v <= 10:
            msg = "NPS score must be 0–10"
            raise ValueError(msg)
        return v


class NPSSurveyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    customer_email: str
    score: int
    category: str
    feedback: str | None
    created_at: datetime


class EmailCampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    subject: str | None = Field(default=None, max_length=500)
    body_html: str | None = Field(default=None)
    campaign_type: EmailCampaignType = EmailCampaignType.NEWSLETTER
    target_segment: str | None = Field(default="all", max_length=50)
    scheduled_at: datetime | None = None

    @field_validator("subject", "body_html", mode="before")
    @classmethod
    def blank_to_none(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            msg = "Campaign name must not be blank"
            raise ValueError(msg)
        return cleaned


class ContentCalendarPromoteRequest(BaseModel):
    auto_publish: bool = False


class EmailCampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    name: str
    subject: str
    campaign_type: EmailCampaignType
    status: EmailCampaignStatus
    target_segment: str | None
    scheduled_at: datetime | None
    sent_at: datetime | None
    recipient_count: int
    open_count: int
    click_count: int
    unsubscribe_count: int
    created_at: datetime


class ContentCalendarCreate(BaseModel):
    days_ahead: int = Field(default=7, ge=1, le=90)
    platforms: list[str] = Field(default=["instagram", "facebook"])

    @field_validator("platforms")
    @classmethod
    def validate_platforms(cls, v: list[str]) -> list[str]:
        allowed = {"instagram", "facebook", "twitter", "email", "all"}
        invalid = set(v) - allowed
        if invalid:
            msg = f"Invalid platforms: {invalid}. Allowed: {allowed}"
            raise ValueError(msg)
        return v


class ContentCalendarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    title: str
    content_type: str
    platform: str
    draft_content: str
    hashtags: list[str] | None
    scheduled_date: str | None
    status: str
    occasion: str | None
    created_at: datetime


class LoyaltyConfigUpdate(BaseModel):
    points_per_dollar: float = Field(default=1.0, ge=0.1, le=100.0)
    redemption_rate: float = Field(default=0.01, ge=0.001, le=1.0)  # $ per point
    tier_thresholds: dict[str, int] = Field(
        default={"bronze": 0, "silver": 500, "gold": 1500, "platinum": 5000}
    )
