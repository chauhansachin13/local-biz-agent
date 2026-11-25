"""Unit tests for the BizPresence AI agent and tool modules."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.booking_agent import BookingAgent
from src.agents.orchestrator import BizPresenceOrchestrator
from src.agents.review_agent import ReviewAgent
from src.agents.social_agent import SocialMediaAgent
from src.models.review import Sentiment
from src.tools.analytics_tools import aggregate_platform_metrics
from src.tools.content_tools import generate_post_ideas, generate_promotional_offer
from src.tools.google_tools import get_business_insights, update_business_profile
from src.tools.review_tools import analyze_review_sentiment
from src.utils.helpers import format_phone, generate_slug, truncate_text, validate_email

# ---------------------------------------------------------------------------
# Helper / Utility Tests
# ---------------------------------------------------------------------------


def test_generate_slug() -> None:
    assert generate_slug("Chai Junction Pune") == "chai-junction-pune"
    assert generate_slug("  Hello World!  ") == "hello-world"
    assert generate_slug("") == ""


def test_format_phone_india() -> None:
    result = format_phone("9876543210")
    assert result == "+91 98765 43210"


def test_validate_email_valid() -> None:
    assert validate_email("hello@example.com") is True
    assert validate_email("user+tag@domain.co.in") is True


def test_validate_email_invalid() -> None:
    assert validate_email("not-an-email") is False
    assert validate_email("") is False
    assert validate_email("@domain.com") is False


def test_truncate_text() -> None:
    assert truncate_text("Hello World", max_len=5) == "He..."
    assert truncate_text("Short", max_len=100) == "Short"
    assert truncate_text("", max_len=10) == ""


# ---------------------------------------------------------------------------
# Tool Tests (mock/stub mode)
# ---------------------------------------------------------------------------


def test_update_business_profile_tool() -> None:
    """Verify the Google Business profile tool returns structured mock output."""
    result = update_business_profile.invoke(
        {"business_data": {"name": "Test Biz", "category": "Cafe"}}
    )
    assert "success" in result
    assert "Test Biz" in result or "updated" in result.lower()


def test_get_business_insights_tool() -> None:
    """Verify insights tool returns a dict with views and metrics."""
    result = get_business_insights.invoke({"location_id": "loc_test123", "days": 30})
    assert isinstance(result, dict)
    assert result["status"] == "success"


def test_analyze_review_sentiment_tool() -> None:
    """Verify sentiment analysis tool returns expected structure."""
    result = analyze_review_sentiment.invoke(
        {"review_text": "Absolutely wonderful food and service!", "rating": 5}
    )
    assert isinstance(result, dict)
    assert "sentiment" in result
    assert result["sentiment"] in ("positive", "negative", "neutral", "mixed")


def test_generate_post_ideas_tool() -> None:
    """Verify post ideas tool returns a list."""
    result = generate_post_ideas.invoke({"business_type": "Italian Restaurant", "count": 3})
    assert isinstance(result, list)
    assert len(result) >= 1


def test_generate_promotional_offer_tool() -> None:
    """Verify promo offer tool returns a string with the business name."""
    result = generate_promotional_offer.invoke(
        {"business_name": "Bella Napoli", "occasion": "Holiday Season"}
    )
    assert isinstance(result, str)
    assert "Bella Napoli" in result


def test_aggregate_platform_metrics_tool() -> None:
    """Verify analytics aggregation returns structured metrics."""
    result = aggregate_platform_metrics.invoke({"business_id": "1", "days": 7})
    assert isinstance(result, dict)
    assert "google_business" in result or "social_media" in result


# ---------------------------------------------------------------------------
# Agent Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_social_agent_generate_post() -> None:
    """Verify SocialMediaAgent generates a post with content and hashtags."""
    agent = SocialMediaAgent()
    business = MagicMock()
    business.name = "Test Cafe"
    business.category = "Cafe"
    business.city = "Mumbai"
    business.state = "MH"
    business.description = "Best coffee in town"
    business.website = "https://testcafe.com"
    business.phone = "9876543210"

    with patch(
        "src.agents.social_agent.generate_text_with_llm", new_callable=AsyncMock
    ) as mock_llm:
        mock_llm.return_value = "Start your morning with the best brew in Mumbai!"
        result = await agent.generate_post(
            business=business, platform="instagram", topic="Morning coffee"
        )

    assert result["platform"] == "instagram"
    assert "Mumbai" in result["content"]
    assert isinstance(result["hashtags"], list)
    assert "best_time_to_post" in result


def test_review_agent_sentiment_classification() -> None:
    """Verify ReviewAgent classifies positive, neutral, and negative reviews."""
    agent = ReviewAgent()
    assert (
        agent.analyze_sentiment(5, "Amazing food and super friendly staff!") == Sentiment.POSITIVE
    )
    assert (
        agent.analyze_sentiment(1, "Terrible wait, cold food, and rude service.")
        == Sentiment.NEGATIVE
    )
    assert agent.analyze_sentiment(3, "Food was okay.") == Sentiment.NEUTRAL


@pytest.mark.asyncio
async def test_review_agent_draft_response_fallback() -> None:
    """Verify ReviewAgent falls back cleanly when LLM is unconfigured."""
    agent = ReviewAgent()
    business = MagicMock()
    business.name = "Test Cafe"
    business.category = "Cafe"
    business.email = "hi@testcafe.com"
    business.phone = None

    review = MagicMock()
    review.reviewer_name = "Jordan Lee"
    review.rating = 2
    review.platform = "google"
    review.review_text = "Wait was very long."

    with patch(
        "src.agents.review_agent.generate_text_with_llm", new_callable=AsyncMock
    ) as mock_llm:
        mock_llm.return_value = None
        reply = await agent.draft_response(business=business, review=review)

    assert "Jordan" in reply
    assert "Test Cafe" in reply
    assert "apologies" in reply.lower()


@pytest.mark.asyncio
async def test_booking_agent_day_hours_and_closed(db_session, sample_business) -> None:
    """Verify BookingAgent respects operating hours and closed days."""
    agent = BookingAgent()
    sample_business.operating_hours = {
        "monday": {"open": "09:00", "close": "12:00", "closed": False},
        "tuesday": {"open": "09:00", "close": "12:00", "closed": True},
    }
    today = date.today()
    # Find next Tuesday
    days_until_tue = (1 - today.weekday()) % 7
    next_tue = today + timedelta(days=days_until_tue)
    avail = await agent.get_availability(db_session, sample_business, next_tue)
    assert avail["is_open"] is False
    assert avail["available_count"] == 0


# ---------------------------------------------------------------------------
# Orchestrator Intent Classification Tests
# ---------------------------------------------------------------------------


def test_orchestrator_classifies_social_intent() -> None:
    """Verify orchestrator correctly identifies social media intents."""
    orchestrator = BizPresenceOrchestrator()
    assert (
        orchestrator._classify_intent("create an instagram post about our sale") == "social_create"
    )
    assert orchestrator._classify_intent("post a tweet about new menu") == "social_create"


def test_orchestrator_classifies_review_intent() -> None:
    """Verify orchestrator correctly identifies review intents."""
    orchestrator = BizPresenceOrchestrator()
    assert orchestrator._classify_intent("respond to our pending reviews") == "review_respond"
    assert orchestrator._classify_intent("reply to the negative feedback") == "review_respond"


def test_orchestrator_classifies_booking_intent() -> None:
    """Verify orchestrator correctly identifies booking intents."""
    orchestrator = BizPresenceOrchestrator()
    assert orchestrator._classify_intent("show today's bookings") == "booking_manage"
    assert (
        orchestrator._classify_intent("what appointments do we have tomorrow") == "booking_manage"
    )
