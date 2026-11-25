"""Integration tests for the BizPresence AI FastAPI endpoints."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.models import Booking, Business, Review


def test_health_check(test_client: TestClient) -> None:
    """Verify the /health endpoint reports a healthy service status."""
    response = test_client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"


def test_create_business(test_client: TestClient) -> None:
    """Verify POST /api/v1/businesses creates a new local business record."""
    body = {
        "name": "Velvet Bloom Florist",
        "category": "Flower Shop",
        "description": "Custom seasonal bouquets and event floral arrangements.",
        "address": "118 Oak Avenue, Seattle, WA 98101",
        "phone": "+1-206-555-0142",
        "website": "https://velvetbloom.example.com",
        "hours": "Tue-Sat 09:00-18:00",
    }

    response = test_client.post("/api/v1/businesses", json=body)

    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["name"] == body["name"]
    assert data["category"] == body["category"]


def test_get_business(test_client: TestClient, sample_business: Business) -> None:
    """Verify GET /api/v1/businesses/{id} retrieves the expected business."""
    response = test_client.get(f"/api/v1/businesses/{sample_business.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sample_business.id
    assert data["name"] == sample_business.name
    assert data["hours"] == sample_business.hours


def test_get_business_not_found(test_client: TestClient) -> None:
    """Verify GET /api/v1/businesses/{id} returns 404 for a nonexistent business."""
    response = test_client.get("/api/v1/businesses/999999")

    assert response.status_code == 404


def test_create_social_post(test_client: TestClient, sample_business: Business) -> None:
    """Verify POST /api/v1/posts persists a new social media post for a business."""
    body = {
        "business_id": sample_business.id,
        "platform": "instagram",
        "content": "Weekend cinnamon brioche drops at 8 AM sharp!",
        "hashtags": "#Brioche #AustinBakery #WeekendTreats",
        "status": "scheduled",
    }

    response = test_client.post("/api/v1/posts", json=body)

    assert response.status_code == 201
    data = response.json()
    assert data["business_id"] == sample_business.id
    assert data["platform"] == "instagram"
    assert data["status"] == "scheduled"


def test_list_reviews(
    test_client: TestClient,
    sample_business: Business,
    sample_review: Review,
) -> None:
    """Verify GET /api/v1/reviews lists reviews filtered by business_id."""
    response = test_client.get(
        "/api/v1/reviews",
        params={"business_id": sample_business.id},
    )

    assert response.status_code == 200
    reviews = response.json()
    assert isinstance(reviews, list)
    assert len(reviews) == 1
    assert reviews[0]["id"] == sample_review.id
    assert reviews[0]["author_name"] == sample_review.author_name
    assert reviews[0]["sentiment"] == "positive"


def test_create_booking(test_client: TestClient, sample_business: Business) -> None:
    """Verify POST /api/v1/bookings creates an appointment on an open time slot."""
    scheduled_at = (
        datetime.now(timezone.utc).replace(hour=11, minute=0, second=0, microsecond=0)
        + timedelta(days=3)
    ).isoformat()
    body = {
        "business_id": sample_business.id,
        "customer_name": "Elena Gomez",
        "customer_email": "elena.gomez@example.com",
        "service_name": "Wedding Cake Consultation",
        "scheduled_at": scheduled_at,
        "duration_minutes": 45,
    }

    response = test_client.post("/api/v1/bookings", json=body)

    assert response.status_code == 201
    data = response.json()
    assert data["business_id"] == sample_business.id
    assert data["customer_name"] == "Elena Gomez"
    assert data["status"] == "confirmed"


def test_create_booking_conflict_returns_409(
    test_client: TestClient,
    sample_business: Business,
    sample_booking: Booking,
) -> None:
    """Verify POST /api/v1/bookings rejects overlapping appointments with 409 Conflict."""
    body = {
        "business_id": sample_business.id,
        "customer_name": "Sam Patel",
        "customer_email": "sam.patel@example.com",
        "service_name": "Bread Workshop",
        "scheduled_at": sample_booking.scheduled_at.isoformat(),
        "duration_minutes": 30,
    }

    response = test_client.post("/api/v1/bookings", json=body)

    assert response.status_code == 409


def test_agent_chat(test_client: TestClient, sample_business: Business) -> None:
    """Verify POST /api/v1/agent/chat routes natural-language prompts via Orchestrator."""
    mocked_result = {
        "routed_agent": "content_agent",
        "intent": "content",
        "reply": "Here is an Instagram caption for Sunrise Artisan Bakery's weekend special!",
        "metadata": {"platform": "instagram"},
    }

    with patch(
        "app.routers.agent.orchestrator.route",
        return_value=mocked_result,
    ) as mock_route:
        response = test_client.post(
            "/api/v1/agent/chat",
            json={
                "business_id": sample_business.id,
                "message": "Create an Instagram post for our weekend sourdough special",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["routed_agent"] == "content_agent"
    assert data["intent"] == "content"
    assert "Sunrise Artisan Bakery" in data["reply"]
    mock_route.assert_called_once()


def test_update_business_profile(
    test_client: TestClient,
    sample_business: Business,
) -> None:
    """Verify PATCH /api/v1/businesses/{id} updates business hours and description."""
    response = test_client.patch(
        f"/api/v1/businesses/{sample_business.id}",
        json={"hours": "Mon-Sun 06:30-19:00"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["hours"] == "Mon-Sun 06:30-19:00"
