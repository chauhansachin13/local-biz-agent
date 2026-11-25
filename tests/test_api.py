"""Integration tests for the BizPresence AI FastAPI endpoints."""

from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient

from src.models.booking import Booking
from src.models.business import Business
from src.models.review import Review
from src.models.social_post import SocialPost

pytestmark = pytest.mark.asyncio(loop_scope="function")


async def test_root_endpoint(test_client: AsyncClient) -> None:
    """Verify the root / endpoint returns API metadata."""
    response = await test_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "BizPresence AI"
    assert data["status"] == "healthy"
    assert "storefront" in data["endpoints"]


async def test_health_check(test_client: AsyncClient) -> None:
    """Verify the /health endpoint reports healthy status."""
    response = await test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


async def test_create_and_list_business(test_client: AsyncClient) -> None:
    """Verify POST and GET /api/businesses/ register and list businesses."""
    body = {
        "name": "Velvet Bloom Florist",
        "category": "Flower Shop",
        "description": "Custom seasonal bouquets and event floral arrangements.",
        "address": "118 Oak Avenue",
        "city": "Seattle",
        "state": "WA",
        "zip_code": "98101",
        "phone": "+1-206-555-0142",
        "email": "hello@velvetbloom.com",
    }
    response = await test_client.post("/api/businesses/", json=body)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["name"] == body["name"]
    assert data["category"] == body["category"]

    list_resp = await test_client.get("/api/businesses/")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["name"] == body["name"]


async def test_get_update_and_gbp_setup_business(
    test_client: AsyncClient, sample_business: Business
) -> None:
    """Verify business get, update, Google Business setup, and dashboard overview."""
    get_resp = await test_client.get(f"/api/businesses/{sample_business.id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == sample_business.name

    upd_resp = await test_client.put(
        f"/api/businesses/{sample_business.id}",
        json={"description": "Organic sourdough and single-origin espresso."},
    )
    assert upd_resp.status_code == 200
    assert "Organic sourdough" in upd_resp.json()["description"]

    gbp_resp = await test_client.post(
        f"/api/businesses/{sample_business.id}/setup-google",
        json={"primary_category": "Artisan Bakery", "verify_now": True},
    )
    assert gbp_resp.status_code == 200
    assert gbp_resp.json()["status"] == "verified"
    assert gbp_resp.json()["completeness_score"] == 100

    dash_resp = await test_client.get(f"/api/businesses/{sample_business.id}/dashboard")
    assert dash_resp.status_code == 200
    assert dash_resp.json()["google_profile_status"] == "verified"


async def test_get_business_not_found(test_client: AsyncClient) -> None:
    """Verify GET /api/businesses/{id} returns 404 for nonexistent business."""
    response = await test_client.get("/api/businesses/999999")
    assert response.status_code == 404


async def test_social_post_schedule_calendar_and_generate(
    test_client: AsyncClient,
    sample_business: Business,
    sample_post: SocialPost,
) -> None:
    """Verify social post creation, scheduling, listing, calendar, and AI generation."""
    create_resp = await test_client.post(
        f"/api/social/{sample_business.id}/post",
        json={
            "platform": "instagram",
            "content": "Fresh cinnamon rolls every Saturday morning!",
            "status": "published",
        },
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["status"] == "published"

    sched_dt = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    sched_resp = await test_client.post(
        f"/api/social/{sample_business.id}/schedule",
        json={
            "platform": "facebook",
            "content": "Sunday coffee tasting event!",
            "scheduled_at": sched_dt,
        },
    )
    assert sched_resp.status_code == 201
    assert sched_resp.json()["status"] == "scheduled"

    list_resp = await test_client.get(f"/api/social/{sample_business.id}/posts")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 3

    cal_resp = await test_client.get(f"/api/social/{sample_business.id}/calendar?days=14")
    assert cal_resp.status_code == 200
    assert cal_resp.json()["total_posts"] >= 2

    gen_resp = await test_client.post(
        f"/api/social/{sample_business.id}/generate-content",
        json={"platform": "instagram", "topic": "Weekend Sourdough Drop"},
    )
    assert gen_resp.status_code == 200
    assert len(gen_resp.json()["content"]) > 0
    assert len(gen_resp.json()["hashtags"]) > 0


async def test_reviews_respond_auto_respond_and_analytics(
    test_client: AsyncClient,
    sample_business: Business,
    sample_review: Review,
) -> None:
    """Verify review listing, AI reply, and review analytics."""
    list_resp = await test_client.get(f"/api/reviews/{sample_business.id}/reviews")
    assert list_resp.status_code == 200
    reviews = list_resp.json()
    assert len(reviews) == 1
    assert reviews[0]["reviewer_name"] == sample_review.reviewer_name

    respond_resp = await test_client.post(
        f"/api/reviews/{sample_business.id}/reviews/{sample_review.id}/respond",
        json={"use_ai": True},
    )
    assert respond_resp.status_code == 200
    assert respond_resp.json()["response_status"] == "responded"
    assert len(respond_resp.json()["response_text"]) > 0

    analytics_resp = await test_client.get(f"/api/reviews/{sample_business.id}/reviews/analytics")
    assert analytics_resp.status_code == 200
    an = analytics_resp.json()
    assert an["total_reviews"] == 1
    assert an["average_rating"] == 5.0
    assert an["response_rate"] == 100.0


async def test_bookings_create_conflict_cancel_and_availability(
    test_client: AsyncClient,
    sample_business: Business,
    sample_booking: Booking,
) -> None:
    """Verify booking creation, conflict 409 rejection, cancellation, and availability."""
    list_resp = await test_client.get(f"/api/bookings/{sample_business.id}/bookings")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    conflict_resp = await test_client.post(
        f"/api/bookings/{sample_business.id}/book",
        json={
            "customer_name": "Sam Patel",
            "customer_email": "sam@example.com",
            "customer_phone": "+1-512-555-0188",
            "service": "Bread Tasting",
            "booking_date": sample_booking.booking_date.isoformat(),
            "booking_time": "14:00:00",
            "duration_minutes": 30,
        },
    )
    assert conflict_resp.status_code == 409

    open_date = (date.today() + timedelta(days=3)).isoformat()
    create_resp = await test_client.post(
        f"/api/bookings/{sample_business.id}/book",
        json={
            "customer_name": "Elena Gomez",
            "customer_email": "elena@example.com",
            "customer_phone": "+1-512-555-0177",
            "service": "Cake Consultation",
            "booking_date": open_date,
            "booking_time": "11:00:00",
            "duration_minutes": 60,
        },
    )
    assert create_resp.status_code == 201
    created_id = create_resp.json()["id"]

    cancel_resp = await test_client.delete(
        f"/api/bookings/{sample_business.id}/bookings/{created_id}"
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    avail_resp = await test_client.get(
        f"/api/bookings/{sample_business.id}/availability",
        params={"date": open_date, "duration_minutes": 60},
    )
    assert avail_resp.status_code == 200
    assert avail_resp.json()["available_count"] > 0


async def test_orders_and_public_storefront(
    test_client: AsyncClient,
    sample_business: Business,
) -> None:
    """Verify online order lifecycle and customer-facing HTML storefront."""
    order_resp = await test_client.post(
        f"/api/orders/{sample_business.id}/order",
        json={
            "customer_name": "Priya Verma",
            "customer_phone": "+91 98765 43210",
            "fulfillment_type": "pickup",
            "items": [{"name": "Sourdough Loaf", "quantity": 2, "price": 9.5}],
        },
    )
    assert order_resp.status_code == 201
    order_data = order_resp.json()
    assert order_data["total_amount"] == 19.0
    assert order_data["status"] == "new"

    list_resp = await test_client.get(f"/api/orders/{sample_business.id}/orders")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    upd_resp = await test_client.put(
        f"/api/orders/{sample_business.id}/orders/{order_data['id']}",
        json={"status": "ready"},
    )
    assert upd_resp.status_code == 200
    assert upd_resp.json()["status"] == "ready"

    site_resp = await test_client.get(f"/site/{sample_business.id}")
    assert site_resp.status_code == 200
    assert sample_business.name in site_resp.text
    assert "Place an Online Order" in site_resp.text


async def test_agent_langgraph_chat_memory_hitl_and_logs(
    test_client: AsyncClient,
    sample_business: Business,
    sample_review: Review,
) -> None:
    """Verify LangGraph multi-step chat, memory persistence, HITL approvals, and run logs."""
    # Compound request in Copilot mode (auto_execute=False) -> plans 2 tasks + queues approval
    chat_resp = await test_client.post(
        f"/api/agent/{sample_business.id}/chat",
        json={
            "message": "Create an Instagram post about our weekend special and show today's bookings",
            "auto_execute": False,
            "session_id": "test_sess",
        },
    )
    assert chat_resp.status_code == 200
    cdata = chat_resp.json()
    assert len(cdata["plan"]) >= 2
    assert len(cdata["agent_trace"]) >= 3
    assert len(cdata["queued_approvals"]) == 1
    assert cdata["health_score"] is not None

    # Persistent memory check
    hist_resp = await test_client.get(
        f"/api/agent/{sample_business.id}/history", params={"session_id": "test_sess"}
    )
    assert hist_resp.status_code == 200
    assert len(hist_resp.json()) == 2

    # Approve queued HITL action with edited copy
    action_id = cdata["queued_approvals"][0]["id"]
    dec_resp = await test_client.post(
        f"/api/agent/{sample_business.id}/approvals/{action_id}/decide",
        json={"decision": "approve", "edited_content": "Approved weekend sourdough drop!"},
    )
    assert dec_resp.status_code == 200
    assert dec_resp.json()["status"] == "executed"

    # Run logs check
    logs_resp = await test_client.get(f"/api/agent/{sample_business.id}/logs")
    assert logs_resp.status_code == 200
    assert len(logs_resp.json()) >= 2


async def test_magic_onboard_campaign_health_and_autopilot(
    test_client: AsyncClient,
) -> None:
    """Verify 60-sec magic onboarding, health score, campaign launcher, and autopilot cycle."""
    onboard_resp = await test_client.post(
        "/api/agent/magic-onboard",
        json={
            "name": "Chai Junction",
            "category": "cafe",
            "city": "Pune",
            "state": "Maharashtra",
            "phone": "9876543210",
            "specialty": "Masala chai and bun maska",
        },
    )
    assert onboard_resp.status_code == 201
    odata = onboard_resp.json()
    biz_id = odata["business"]["id"]
    assert odata["starter_posts_created"] == 3
    assert odata["catalog_items_created"] >= 2
    assert odata["health_score"] > 50

    hs_resp = await test_client.get(f"/api/agent/{biz_id}/health-score")
    assert hs_resp.status_code == 200
    assert len(hs_resp.json()["pillars"]) == 5

    camp_resp = await test_client.post(
        f"/api/agent/{biz_id}/campaign",
        json={
            "occasion": "Monsoon Chai Fest",
            "offer_details": "Free bun maska with 2 masala chais",
            "platforms": ["instagram", "google"],
            "auto_execute": False,
        },
    )
    assert camp_resp.status_code == 200
    assert camp_resp.json()["approvals_queued"] == 2

    ap_resp = await test_client.post(f"/api/agent/{biz_id}/autopilot/run")
    assert ap_resp.status_code == 200
    assert ap_resp.json()["autopilot_enabled"] is True
