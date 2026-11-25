"""Database models and Pydantic schemas for Agentic AI memory, HITL approvals, logs, and online orders."""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database.db import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ApprovalStatus(enum.StrEnum):
    """Status of a human-in-the-loop agent approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"


class RiskLevel(enum.StrEnum):
    """Risk classification for agentic guardrails."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OrderStatus(enum.StrEnum):
    """Lifecycle status of an online customer order."""

    NEW = "new"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    READY = "ready"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class FulfillmentType(enum.StrEnum):
    """Fulfillment option for online customer orders."""

    PICKUP = "pickup"
    DELIVERY = "delivery"
    DINE_IN = "dine_in"


class BusinessAgentConfig(Base):
    """Per-business autopilot rules, brand voice, language, and catalog items."""

    __tablename__ = "business_agent_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    autopilot_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_publish_scheduled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_reply_positive_reviews: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    require_approval_negative_reviews: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    preferred_language: Mapped[str] = mapped_column(String(40), nullable=False, default="English")
    brand_voice: Mapped[str] = mapped_column(
        String(120), nullable=False, default="warm, helpful, and neighborhood-friendly"
    )
    catalog_items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    faqs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


class AgentThreadMessage(Base):
    """Persistent conversational memory for a business across chat turns."""

    __tablename__ = "agent_thread_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(
        String(100), nullable=False, default="default", index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(80), nullable=True)
    agent_trace: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


class AgentApprovalAction(Base):
    """Human-in-the-loop (HITL) approval queue for high-impact or copilot actions."""

    __tablename__ = "agent_approval_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    agent_name: Mapped[str] = mapped_column(String(80), nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel, native_enum=False), nullable=False, default=RiskLevel.MEDIUM
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, native_enum=False),
        nullable=False,
        default=ApprovalStatus.PENDING,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentRunLog(Base):
    """Execution audit trail capturing multi-agent planning and tool calls."""

    __tablename__ = "agent_run_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trigger_source: Mapped[str] = mapped_column(String(40), nullable=False, default="chat")
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    agents_invoked: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    tools_called: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    steps_summary: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False, default="completed")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


class OrderRequest(Base):
    """SQLAlchemy ORM model representing an online customer order or service request."""

    __tablename__ = "order_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(30), nullable=False)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    fulfillment_type: Mapped[FulfillmentType] = mapped_column(
        Enum(FulfillmentType, native_enum=False),
        nullable=False,
        default=FulfillmentType.PICKUP,
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, native_enum=False),
        nullable=False,
        default=OrderStatus.NEW,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


class WhatsAppMessage(Base):
    """WhatsApp / SMS concierge conversation log for customers and owners."""

    __tablename__ = "whatsapp_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_phone: Mapped[str] = mapped_column(String(30), nullable=False)
    sender_name: Mapped[str] = mapped_column(String(120), nullable=False, default="Guest")
    sender_role: Mapped[str] = mapped_column(String(20), nullable=False, default="customer")
    direction: Mapped[str] = mapped_column(String(20), nullable=False, default="inbound")
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    agent_used: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class BusinessAgentConfigResponse(BaseModel):
    """Response schema for business agent & autopilot configuration."""

    model_config = ConfigDict(from_attributes=True)

    business_id: int
    autopilot_enabled: bool
    auto_publish_scheduled: bool
    auto_reply_positive_reviews: bool
    require_approval_negative_reviews: bool
    preferred_language: str
    brand_voice: str
    catalog_items: list[dict[str, Any]]
    faqs: list[dict[str, Any]]
    updated_at: datetime


class BusinessAgentConfigUpdate(BaseModel):
    """Update payload for business agent configuration and catalog."""

    autopilot_enabled: bool | None = None
    auto_publish_scheduled: bool | None = None
    auto_reply_positive_reviews: bool | None = None
    require_approval_negative_reviews: bool | None = None
    preferred_language: str | None = Field(default=None, max_length=40)
    brand_voice: str | None = Field(default=None, max_length=120)
    catalog_items: list[dict[str, Any]] | None = None
    faqs: list[dict[str, Any]] | None = None


class AgentThreadMessageResponse(BaseModel):
    """Chat memory message schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    session_id: str
    role: str
    content: str
    intent: str | None = None
    agent_trace: list[dict[str, Any]]
    created_at: datetime


class AgentApprovalResponse(BaseModel):
    """HITL approval queue item response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    action_type: str
    title: str
    description: str
    agent_name: str
    reasoning: str
    risk_level: RiskLevel
    payload: dict[str, Any]
    status: ApprovalStatus
    created_at: datetime
    decided_at: datetime | None = None


class ApprovalDecisionRequest(BaseModel):
    """Approve or reject a queued HITL agent action, optionally editing its content."""

    decision: str = Field(..., pattern="^(approve|reject)$")
    edited_content: str | None = None


class AgentRunLogResponse(BaseModel):
    """Agent execution audit log response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    trigger_source: str
    goal: str
    agents_invoked: list[str]
    tools_called: list[str]
    steps_summary: list[dict[str, Any]]
    outcome: str
    duration_ms: int
    created_at: datetime


class OrderItemSchema(BaseModel):
    """Single item in an online customer order."""

    name: str = Field(..., min_length=1, max_length=200)
    quantity: int = Field(default=1, ge=1, le=100)
    price: float = Field(default=0.0, ge=0.0)


class OrderCreateRequest(BaseModel):
    """Payload to submit an online customer order."""

    customer_name: str = Field(..., min_length=1, max_length=255)
    customer_phone: str = Field(..., min_length=5, max_length=30)
    customer_email: str | None = Field(default=None, max_length=255)
    items: list[OrderItemSchema] = Field(..., min_length=1)
    fulfillment_type: FulfillmentType = FulfillmentType.PICKUP
    notes: str | None = None


class OrderStatusUpdate(BaseModel):
    """Payload to update online order status."""

    status: OrderStatus
    notes: str | None = None


class OrderResponse(BaseModel):
    """Online order API response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    customer_name: str
    customer_phone: str
    customer_email: str | None = None
    items: list[dict[str, Any]]
    total_amount: float
    fulfillment_type: FulfillmentType
    status: OrderStatus
    notes: str | None = None
    created_at: datetime


class WhatsAppInboundRequest(BaseModel):
    """Inbound WhatsApp message payload (customer inquiry or owner command)."""

    sender_phone: str = Field(default="+91 98765 43210", min_length=5, max_length=30)
    sender_name: str = Field(default="Guest", min_length=1, max_length=120)
    sender_role: str = Field(default="customer", pattern="^(customer|owner)$")
    message: str = Field(..., min_length=1)


class WhatsAppMessageResponse(BaseModel):
    """Stored WhatsApp conversation entry."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    sender_phone: str
    sender_name: str
    sender_role: str
    direction: str
    message_text: str
    agent_used: str | None = None
    created_at: datetime
