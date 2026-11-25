"""Additional API request/response schemas for dashboard, AI generation, analytics, and agent endpoints."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, Field

from src.models.business import BusinessResponse
from src.models.social_post import SocialPlatform, SocialPostResponse

# ---------------------------------------------------------------------------
# Business Setup & Dashboard Schemas
# ---------------------------------------------------------------------------


class GoogleSetupRequest(BaseModel):
    """Payload to configure/verify a Google Business Profile."""

    google_business_id: str | None = None
    primary_category: str | None = None
    attributes: list[str] = Field(default_factory=list)
    service_area: str = ""
    verify_now: bool = True


class GoogleSetupResponse(BaseModel):
    """Result of Google Business Profile configuration."""

    business_id: int
    google_business_id: str
    status: str
    completeness_score: int
    checklist: list[dict[str, Any]]


class ActivityItem(BaseModel):
    """Recent activity feed entry."""

    type: str
    title: str
    detail: str
    timestamp: datetime
    status: str = "info"


class DashboardOverviewResponse(BaseModel):
    """Aggregated business dashboard overview."""

    business: BusinessResponse
    total_reviews: int
    average_rating: float
    pending_reviews: int
    posts_this_week: int
    total_posts: int
    scheduled_posts: int
    upcoming_bookings: int
    bookings_today: int
    total_bookings: int
    total_engagement: int
    google_profile_status: str
    recent_activity: list[ActivityItem]


# ---------------------------------------------------------------------------
# Social Media Action Schemas
# ---------------------------------------------------------------------------


class SocialPostCreateRequest(BaseModel):
    """Payload to create/publish a social media post for a business."""

    platform: SocialPlatform = SocialPlatform.INSTAGRAM
    content: str = Field(..., min_length=1)
    image_url: str | None = Field(default=None, max_length=1000)
    status: str = "published"


class SocialPostScheduleRequest(BaseModel):
    """Payload to schedule a social media post."""

    platform: SocialPlatform = SocialPlatform.INSTAGRAM
    content: str = Field(..., min_length=1)
    image_url: str | None = Field(default=None, max_length=1000)
    scheduled_at: datetime


class ContentCalendarDay(BaseModel):
    """Single day in the social content calendar."""

    date: str
    posts: list[SocialPostResponse]


class ContentCalendarResponse(BaseModel):
    """Multi-day content calendar response."""

    business_id: int
    start_date: str
    end_date: str
    total_posts: int
    days: list[ContentCalendarDay]


class GenerateContentRequest(BaseModel):
    """AI content generation prompt."""

    platform: SocialPlatform = SocialPlatform.INSTAGRAM
    topic: str = ""
    tone: str = "friendly and engaging"
    include_hashtags: bool = True
    call_to_action: str = ""


class GenerateContentResponse(BaseModel):
    """AI-generated social media copy and metadata."""

    platform: str
    content: str
    hashtags: list[str]
    best_time_to_post: str
    image_prompt: str


# ---------------------------------------------------------------------------
# Review Action & Analytics Schemas
# ---------------------------------------------------------------------------


class ReviewRespondRequest(BaseModel):
    """Payload to respond to a customer review."""

    response_text: str | None = None
    use_ai: bool = False
    tone: str = "warm and professional"


class AutoRespondRequest(BaseModel):
    """Payload for AI auto-response across pending reviews."""

    only_positive: bool = False
    min_rating: int = Field(default=1, ge=1, le=5)
    max_count: int = Field(default=25, ge=1, le=100)
    tone: str = "warm and professional"


class AutoRespondResponse(BaseModel):
    """Summary of automated review replies."""

    business_id: int
    processed_count: int
    responded_review_ids: list[int]


class ReviewAnalyticsResponse(BaseModel):
    """Aggregated review sentiment, ratings, and platform analytics."""

    business_id: int
    total_reviews: int
    average_rating: float
    response_rate: float
    pending_count: int
    sentiment_breakdown: dict[str, int]
    rating_distribution: dict[str, int]
    platform_breakdown: dict[str, int]
    recent_trend: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Booking Action & Availability Schemas
# ---------------------------------------------------------------------------


class BookingCreateRequest(BaseModel):
    """Payload to create a booking for a business."""

    customer_name: str = Field(..., min_length=1, max_length=255)
    customer_email: str = Field(..., min_length=3, max_length=255)
    customer_phone: str = Field(..., min_length=5, max_length=30)
    service: str = Field(..., min_length=1, max_length=255)
    booking_date: date
    booking_time: time
    duration_minutes: int = Field(default=60, ge=5, le=1440)
    notes: str | None = None


class AvailabilitySlot(BaseModel):
    """Single appointment slot."""

    start_time: str
    end_time: str
    available: bool


class AvailabilityResponse(BaseModel):
    """Availability result for a target date."""

    business_id: int
    date: str
    day_of_week: str
    is_open: bool
    open_time: str | None = None
    close_time: str | None = None
    slots: list[AvailabilitySlot]
    available_count: int


# ---------------------------------------------------------------------------
# AI Agent Schemas
# ---------------------------------------------------------------------------


class AgentChatRequest(BaseModel):
    """Natural language prompt for the BizPresence AI orchestrator."""

    message: str = Field(..., min_length=1)
    auto_execute: bool = True
    context: dict[str, Any] = Field(default_factory=dict)


class AgentChatResponse(BaseModel):
    """Orchestrator chat reply with actions and suggested follow-ups."""

    business_id: int
    reply: str
    intent: str
    actions_taken: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    suggested_followups: list[str] = Field(default_factory=list)


class AgentSuggestion(BaseModel):
    """Proactive AI suggestion for business growth."""

    id: str
    category: str
    priority: str
    title: str
    description: str
    recommended_action: str
    prompt_to_run: str


class AgentSuggestionsResponse(BaseModel):
    """Collection of proactive AI suggestions."""

    business_id: int
    generated_at: datetime
    suggestions: list[AgentSuggestion]
