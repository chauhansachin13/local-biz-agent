"""Unit tests for the BizPresence AI agent and tool modules."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.analytics_agent import create_analytics_agent
from src.agents.booking_agent import BookingAgent
from src.agents.content_generator import create_content_agent
from src.agents.google_business import create_google_business_agent
from src.agents.health_and_growth import compute_health_score
from src.agents.orchestrator import BizPresenceOrchestrator
from src.agents.review_agent import ReviewAgent
from src.agents.review_manager import create_review_agent
from src.agents.seo_audit import generate_daily_brief, run_seo_and_sentiment_audit
from src.agents.social_agent import SocialMediaAgent
from src.agents.social_media import create_social_media_agent
from src.agents.supervisor import _detect_intents_offline
from src.models.review import Sentiment
from src.tools.analytics_tools import (
    aggregate_platform_metrics,
    generate_performance_report,
    identify_trends,
    suggest_data_improvements,
)
from src.tools.content_tools import (
    create_content_calendar,
    generate_blog_outline,
    generate_post_ideas,
    generate_promotional_offer,
)
from src.tools.google_tools import (
    get_business_insights,
    handle_business_qa,
    manage_business_photos,
    post_google_update,
    update_business_hours,
    update_business_profile,
)
from src.tools.review_tools import (
    analyze_review_sentiment,
    fetch_facebook_reviews,
    fetch_google_reviews,
    flag_critical_review,
    get_review_trends,
    respond_to_review,
)
from src.tools.social_tools import (
    get_optimal_posting_times,
    get_social_metrics,
    post_to_facebook,
    post_to_instagram,
    post_to_twitter,
    schedule_post,
)
from src.utils.helpers import format_phone, generate_slug, truncate_text, validate_email
from src.utils.visuals import generate_promo_poster_png, generate_qr_svg

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
# Agent & Supervisor Tests
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
    days_until_tue = (1 - today.weekday()) % 7
    next_tue = today + timedelta(days=days_until_tue)
    avail = await agent.get_availability(db_session, sample_business, next_tue)
    assert avail["is_open"] is False
    assert avail["available_count"] == 0


@pytest.mark.asyncio
async def test_compute_health_score(db_session, sample_business, sample_review) -> None:
    """Verify Digital Presence Health Score returns 0-100 across 5 pillars."""
    score = await compute_health_score(db_session, sample_business)
    assert 0 <= score["overall_score"] <= 100
    assert len(score["pillars"]) == 5
    assert score["grade"] in {"A+", "A", "B", "C", "D"}


def test_supervisor_multi_intent_decomposition() -> None:
    """Verify offline planner decomposes compound prompts into ordered tasks."""
    plan = _detect_intents_offline(
        "create an instagram post about chai and check pending reviews and today's bookings"
    )
    assert "social_create" in plan
    assert "review_respond" in plan
    assert "booking_manage" in plan


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


def test_social_content_and_review_tool_suites() -> None:
    """Exercise social, content, GBP, review, and analytics LangChain tools."""
    assert "published" in post_to_facebook.invoke(
        {"page_id": "pg1", "content": "Hello local fans!"}
    )
    assert "error" in post_to_instagram.invoke({"content": "Photo", "image_url": ""})
    assert "published" in post_to_instagram.invoke(
        {"content": "Fresh coffee", "image_url": "https://img.local/1.jpg", "hashtags": ["Coffee"]}
    )
    assert "error" in post_to_twitter.invoke({"content": "x" * 300})
    assert "published" in post_to_twitter.invoke({"content": "Open till 9 PM!"})
    assert "scheduled" in schedule_post.invoke(
        {"platform": "instagram", "content": "Promo", "scheduled_time": "2026-12-01T10:00:00Z"}
    )
    assert "live_db_metrics" in get_social_metrics.invoke({"platform": "all", "days": 7})
    assert "best_days" in get_optimal_posting_times.invoke({"platform": "instagram"})

    assert "calendar" in create_content_calendar.invoke({"business_id": "1", "weeks": 2})
    assert "seo_titles" in generate_blog_outline.invoke(
        {"topic": "Fresh Bread", "business_name": "Sunrise Bakery"}
    )
    assert "published" in post_google_update.invoke(
        {"location_id": "loc_1", "content": "Open today!"}
    )
    assert "success" in update_business_hours.invoke(
        {"location_id": "loc_1", "hours": {"monday": "09:00-18:00"}}
    )
    assert "added" in manage_business_photos.invoke(
        {"location_id": "loc_1", "action": "add", "photo_url": "https://img.local/a.jpg"}
    )
    assert "questions" in handle_business_qa.invoke({"location_id": "loc_1", "action": "list"})

    assert isinstance(fetch_google_reviews.invoke({"location_id": "loc_1"}), list)
    assert isinstance(fetch_facebook_reviews.invoke({"page_id": "pg_1"}), list)
    assert "published" in respond_to_review.invoke(
        {"platform": "google", "review_id": "g_1", "response": "Thank you!"}
    )
    assert "flagged" in flag_critical_review.invoke(
        {"platform": "google", "review_id": "g_2", "reason": "Cold food"}
    )
    assert "average_rating" in get_review_trends.invoke({"business_id": "1"})

    assert "executive_summary" in generate_performance_report.invoke({"business_id": "1"})
    assert "trends" in identify_trends.invoke({"business_id": "1"})
    assert isinstance(suggest_data_improvements.invoke({"business_id": "1"}), list)


def test_visuals_qr_and_promo_poster() -> None:
    """Verify SVG QR generation and Pillow 1080x1080 PNG promo poster generation."""
    svg = generate_qr_svg("http://localhost:8000/site/1")
    assert "<svg" in svg
    png = generate_promo_poster_png(
        business_name="Chai Junction",
        category="Cafe",
        city="Pune",
        headline="Monsoon Special",
        offer_text="15% off all chai combos!",
        promo_code="CHAI15",
        storefront_url="http://localhost:8000/site/1",
    )
    assert png[:4] == b"\x89PNG"
    assert len(png) > 5000


@pytest.mark.asyncio
async def test_seo_audit_and_daily_brief(db_session, sample_business, sample_review) -> None:
    """Verify local SEO audit and morning executive daily brief."""
    audit = await run_seo_and_sentiment_audit(db_session, sample_business)
    assert "target_local_keywords" in audit
    assert audit["nap_consistency_score"] > 0

    brief = await generate_daily_brief(db_session, sample_business)
    assert brief["business_id"] == sample_business.id
    assert "priority_action" in brief


def test_langgraph_react_agent_factories_wire_cleanly() -> None:
    """Verify all 5 LangGraph ReAct agent factories build with mocked ChatGoogleGenerativeAI."""
    mock_agent = MagicMock()
    with (
        patch("src.agents.google_business.ChatGoogleGenerativeAI"),
        patch("src.agents.google_business.create_react_agent", return_value=mock_agent),
        patch("src.agents.social_media.ChatGoogleGenerativeAI"),
        patch("src.agents.social_media.create_react_agent", return_value=mock_agent),
        patch("src.agents.review_manager.ChatGoogleGenerativeAI"),
        patch("src.agents.review_manager.create_react_agent", return_value=mock_agent),
        patch("src.agents.content_generator.ChatGoogleGenerativeAI"),
        patch("src.agents.content_generator.create_react_agent", return_value=mock_agent),
        patch("src.agents.analytics_agent.ChatGoogleGenerativeAI"),
        patch("src.agents.analytics_agent.create_react_agent", return_value=mock_agent),
    ):
        assert create_google_business_agent() is mock_agent
        assert create_social_media_agent() is mock_agent
        assert create_review_agent() is mock_agent
        assert create_content_agent() is mock_agent
        assert create_analytics_agent() is mock_agent
