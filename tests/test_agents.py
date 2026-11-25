"""Unit tests for the BizPresence AI multi-agent system."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.agents.booking_agent import BookingAgent
from app.agents.content_agent import ContentAgent
from app.agents.orchestrator import OrchestratorAgent
from app.agents.profile_agent import ProfileAgent
from app.agents.review_agent import ReviewAgent


def _mock_llm_response(content: str) -> MagicMock:
    """Build a mock LangChain AIMessage-like response object."""
    response = MagicMock()
    response.content = content
    return response


@pytest.mark.parametrize(
    ("user_prompt", "expected_intent"),
    [
        ("Write an Instagram post for our weekend latte promo", "content"),
        ("Draft a reply to the 2-star Google review from yesterday", "review"),
        ("Check if we have any open slots tomorrow at 3 PM", "booking"),
        ("Update our Google Business description and Sunday hours", "profile"),
    ],
)
def test_orchestrator_routes_to_correct_agent(
    user_prompt: str,
    expected_intent: str,
) -> None:
    """Verify OrchestratorAgent classifies intent and delegates to the matching agent."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = _mock_llm_response(expected_intent)

    mock_content_agent = MagicMock()
    mock_content_agent.run.return_value = {"agent": "content", "output": "Post created"}

    mock_review_agent = MagicMock()
    mock_review_agent.run.return_value = {"agent": "review", "output": "Reply drafted"}

    mock_booking_agent = MagicMock()
    mock_booking_agent.run.return_value = {"agent": "booking", "output": "Slot available"}

    mock_profile_agent = MagicMock()
    mock_profile_agent.run.return_value = {"agent": "profile", "output": "Profile updated"}

    orchestrator = OrchestratorAgent(
        llm=mock_llm,
        agents={
            "content": mock_content_agent,
            "review": mock_review_agent,
            "booking": mock_booking_agent,
            "profile": mock_profile_agent,
        },
    )

    result = orchestrator.route(
        message=user_prompt,
        business_context={"id": 1, "name": "Sunrise Artisan Bakery"},
    )

    assert result["intent"] == expected_intent
    assert result["agent"] == expected_intent
    mock_llm.invoke.assert_called_once()


def test_orchestrator_handles_unknown_intent_gracefully() -> None:
    """Verify OrchestratorAgent falls back safely when the LLM returns an unknown intent."""
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = [
        _mock_llm_response("unrecognized_category"),
        _mock_llm_response("I can help with profiles, social posts, reviews, or bookings."),
    ]

    orchestrator = OrchestratorAgent(llm=mock_llm, agents={})
    result = orchestrator.route(
        message="What is the meaning of life?",
        business_context={"id": 1, "name": "Sunrise Artisan Bakery"},
    )

    assert result["intent"] == "general"
    assert "profiles" in result["output"].lower()
    assert mock_llm.invoke.call_count == 2


def test_content_generator_creates_post() -> None:
    """Verify ContentAgent generates a platform-tailored social post from mocked LLM output."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = _mock_llm_response(
        '{"caption": "Warm rosemary sourdough fresh out of the oven!", '
        '"hashtags": ["#Sourdough", "#ArtisanBakery", "#LocalEats"], '
        '"cta": "Stop by before noon for a free espresso pairing!"}'
    )

    agent = ContentAgent(llm=mock_llm)
    post = agent.create_post(
        business_name="Sunrise Artisan Bakery",
        platform="instagram",
        topic="Weekend sourdough special",
        tone="warm and inviting",
    )

    assert post["platform"] == "instagram"
    assert "sourdough" in post["caption"].lower()
    assert len(post["hashtags"]) == 3
    assert "cta" in post
    mock_llm.invoke.assert_called_once()


def test_content_generator_rejects_empty_topic() -> None:
    """Verify ContentAgent raises ValueError when topic is empty or whitespace."""
    mock_llm = MagicMock()
    agent = ContentAgent(llm=mock_llm)

    with pytest.raises(ValueError, match="topic"):
        agent.create_post(
            business_name="Sunrise Artisan Bakery",
            platform="facebook",
            topic="   ",
        )
    mock_llm.invoke.assert_not_called()


def test_review_sentiment_analysis() -> None:
    """Verify ReviewAgent parses sentiment, score, and urgency from customer feedback."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = _mock_llm_response(
        '{"sentiment": "negative", "score": 0.18, "urgent": true, '
        '"summary": "Customer waited 25 minutes for a cold coffee."}'
    )

    agent = ReviewAgent(llm=mock_llm)
    analysis = agent.analyze_sentiment(
        rating=2,
        comment="Waited 25 minutes and my latte was lukewarm.",
    )

    assert analysis["sentiment"] == "negative"
    assert analysis["score"] == pytest.approx(0.18)
    assert analysis["urgent"] is True
    assert "summary" in analysis
    mock_llm.invoke.assert_called_once()


def test_review_agent_drafts_empathetic_reply() -> None:
    """Verify ReviewAgent drafts a polite, personalized reply using business context."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = _mock_llm_response(
        "Thank you for letting us know, Jordan. We are sorry your latte took too long "
        "and would love to make your next visit right at Sunrise Artisan Bakery."
    )

    agent = ReviewAgent(llm=mock_llm)
    reply = agent.draft_reply(
        business_name="Sunrise Artisan Bakery",
        author_name="Jordan",
        rating=2,
        comment="Long wait and lukewarm coffee.",
    )

    assert "Jordan" in reply
    assert "Sunrise Artisan Bakery" in reply
    mock_llm.invoke.assert_called_once()


def test_booking_availability_check() -> None:
    """Verify BookingAgent identifies open and occupied time slots accurately."""
    target_date = (datetime.now(timezone.utc) + timedelta(days=2)).date()
    existing_bookings = [
        {
            "scheduled_at": datetime(
                target_date.year, target_date.month, target_date.day, 10, 0, tzinfo=timezone.utc
            ),
            "duration_minutes": 60,
        },
        {
            "scheduled_at": datetime(
                target_date.year, target_date.month, target_date.day, 14, 0, tzinfo=timezone.utc
            ),
            "duration_minutes": 60,
        },
    ]

    agent = BookingAgent(llm=MagicMock())
    slots = agent.check_availability(
        target_date=target_date,
        existing_bookings=existing_bookings,
        open_hour=9,
        close_hour=17,
    )

    assert "09:00" in slots
    assert "11:00" in slots
    assert "10:00" not in slots
    assert "14:00" not in slots


def test_booking_availability_conflict_detection() -> None:
    """Verify BookingAgent flags overlapping appointment times as unavailable."""
    requested = datetime(2026, 12, 1, 10, 30, tzinfo=timezone.utc)
    existing = [
        {
            "scheduled_at": datetime(2026, 12, 1, 10, 0, tzinfo=timezone.utc),
            "duration_minutes": 60,
        }
    ]

    agent = BookingAgent(llm=MagicMock())
    is_available = agent.is_slot_available(
        requested_time=requested,
        duration_minutes=30,
        existing_bookings=existing,
    )

    assert is_available is False


def test_profile_agent_optimizes_seo_description() -> None:
    """Verify ProfileAgent enriches a business description with local SEO terms."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = _mock_llm_response(
        "Sunrise Artisan Bakery is Austin's neighborhood destination for organic sourdough, "
        "handcrafted pastries, and single-origin espresso on Maple Street."
    )

    with patch("app.agents.profile_agent.ProfileAgent._build_prompt", return_value="prompt"):
        agent = ProfileAgent(llm=mock_llm)
        optimized = agent.optimize_description(
            business_name="Sunrise Artisan Bakery",
            category="Bakery & Cafe",
            city="Austin, TX",
            current_description="We sell bread and coffee.",
        )

    assert "Austin" in optimized
    assert "sourdough" in optimized.lower()
    mock_llm.invoke.assert_called_once()
