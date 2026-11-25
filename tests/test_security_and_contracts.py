"""Security, injection resilience, contract, boundary, and scheduler regression tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.health_and_growth import get_or_create_agent_config
from src.agents.scheduler import run_autopilot_cycle_for_business
from src.models.agent_models import AgentApprovalAction, AgentRunLog, ApprovalStatus
from src.models.booking import Booking, BookingStatus
from src.models.business import Business
from src.models.review import ResponseStatus, Review, Sentiment
from src.models.social_post import PostStatus, SocialPlatform, SocialPost

pytestmark = pytest.mark.asyncio(loop_scope="function")


async def test_xss_escaping_across_public_storefront_and_poster(
    test_client: AsyncClient,
) -> None:
    """Verify HTML/JS payloads in business and review fields are escaped on storefront routes."""
    xss_script = '<script>window.__xss=1;alert("xss")</script>'
    xss_img = '<img src=x onerror="alert(1)">'

    biz_resp = await test_client.post(
        "/api/businesses/",
        json={
            "name": f"Spice {xss_script} Bistro",
            "category": f"Cafe{xss_img}",
            "description": f"Authentic local snacks {xss_script}",
            "address": "10 Market St",
            "city": f"Pune{xss_img}",
            "state": "MH",
            "zip_code": "411001",
            "phone": "+91-98765-00000",
        },
    )
    assert biz_resp.status_code == 201
    biz_id = biz_resp.json()["id"]

    rev_resp = await test_client.post(
        f"/api/reviews/{biz_id}/submit",
        json={
            "reviewer_name": f"Mallory {xss_img}",
            "rating": 5,
            "review_text": f"Amazing chai {xss_script}",
            "platform": "storefront",
        },
    )
    assert rev_resp.status_code == 201

    site_resp = await test_client.get(f"/site/{biz_id}")
    assert site_resp.status_code == 200
    html_body = site_resp.text
    assert xss_script not in html_body
    assert '<img src=x onerror="alert(1)">' not in html_body
    assert "&lt;script&gt;" in html_body

    poster_resp = await test_client.get(f"/site/{biz_id}/poster")
    assert poster_resp.status_code == 200
    assert xss_script not in poster_resp.text
    assert '<img src=x onerror="alert(1)">' not in poster_resp.text
    assert "&lt;script&gt;" in poster_resp.text


async def test_sql_injection_and_unicode_resilience(
    test_client: AsyncClient,
    sample_business: Business,
) -> None:
    """Verify parameterized queries safely handle SQLi strings and multilingual Unicode input."""
    sqli = "'; DROP TABLE businesses; SELECT * FROM reviews WHERE '1'='1"

    chat_resp = await test_client.post(
        f"/api/agent/{sample_business.id}/chat",
        json={"message": f"Create a post for {sqli}"},
    )
    assert chat_resp.status_code == 200

    wa_resp = await test_client.post(
        f"/api/whatsapp/{sample_business.id}/message",
        json={
            "sender_phone": "+91 98111 22333",
            "sender_name": "अमित शर्मा",
            "sender_role": "customer",
            "message": f"नमस्ते! क्या कल 5 बजे टेबल मिलेगी? 🫖 {sqli}",
        },
    )
    assert wa_resp.status_code == 200
    assert len(wa_resp.json()["reply"]) > 0

    biz_check = await test_client.get(f"/api/businesses/{sample_business.id}")
    assert biz_check.status_code == 200
    assert biz_check.json()["name"] == sample_business.name


async def test_boundary_validation_and_error_contracts(
    test_client: AsyncClient,
    sample_business: Business,
) -> None:
    """Verify invalid ratings, negative prices/quantities, bad query params, and 404 contracts."""
    # Invalid rating bounds
    bad_rating = await test_client.post(
        f"/api/reviews/{sample_business.id}/submit",
        json={"reviewer_name": "Test", "rating": 6, "review_text": "Too high"},
    )
    assert bad_rating.status_code == 422

    zero_rating = await test_client.post(
        f"/api/reviews/{sample_business.id}/submit",
        json={"reviewer_name": "Test", "rating": 0, "review_text": "Too low"},
    )
    assert zero_rating.status_code == 422

    # Invalid order items (empty list / zero qty / negative price)
    bad_order = await test_client.post(
        f"/api/orders/{sample_business.id}/order",
        json={
            "customer_name": "Bad Order",
            "customer_phone": "+1 555 0100",
            "items": [],
        },
    )
    assert bad_order.status_code == 422

    neg_price_order = await test_client.post(
        f"/api/orders/{sample_business.id}/order",
        json={
            "customer_name": "Neg Price",
            "customer_phone": "+1 555 0100",
            "items": [{"name": "Item", "quantity": 1, "price": -5.0}],
        },
    )
    assert neg_price_order.status_code == 422

    # Invalid CSV export dataset name
    bad_export = await test_client.get(
        f"/api/businesses/{sample_business.id}/export", params={"dataset": "../../etc/passwd"}
    )
    assert bad_export.status_code == 422

    # Nonexistent IDs across modules return 404 (never 500)
    for url in (
        "/api/businesses/999999",
        "/api/agent/999999/health-score",
        "/api/agent/999999/seo-audit",
        "/api/agent/999999/daily-brief",
        "/api/crm/999999/customers",
        "/api/orders/999999/orders",
        "/site/999999",
        "/site/999999/qr",
        "/site/999999/poster",
    ):
        resp = await test_client.get(url)
        assert resp.status_code == 404, f"Expected 404 for {url}, got {resp.status_code}"

    # Invalid decision enum
    bad_dec = await test_client.post(
        f"/api/agent/{sample_business.id}/approvals/1/decide",
        json={"decision": "auto_hack"},
    )
    assert bad_dec.status_code == 422


async def test_openapi_schema_contract(test_client: AsyncClient) -> None:
    """Verify OpenAPI 3.x document compiles cleanly with expected endpoint coverage."""
    resp = await test_client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"] == "BizPresence AI"
    assert len(spec["paths"]) >= 45


async def test_hitl_approval_reject_and_double_decide_guards(
    test_client: AsyncClient,
    sample_business: Business,
) -> None:
    """Verify HITL rejection prevents publication and double-decision returns 400."""
    chat_resp = await test_client.post(
        f"/api/agent/{sample_business.id}/chat",
        json={"message": "Create a Facebook promo post", "auto_execute": False},
    )
    assert chat_resp.status_code == 200
    approvals = chat_resp.json()["queued_approvals"]
    assert len(approvals) >= 1
    action_id = approvals[0]["id"]

    # First reject -> status becomes rejected, no new post published
    posts_before = await test_client.get(f"/api/social/{sample_business.id}/posts")
    rej_resp = await test_client.post(
        f"/api/agent/{sample_business.id}/approvals/{action_id}/decide",
        json={"decision": "reject"},
    )
    assert rej_resp.status_code == 200
    assert rej_resp.json()["status"] == "rejected"

    posts_after = await test_client.get(f"/api/social/{sample_business.id}/posts")
    assert len(posts_after.json()) == len(posts_before.json())

    # Second decision attempt must fail with 400
    second_resp = await test_client.post(
        f"/api/agent/{sample_business.id}/approvals/{action_id}/decide",
        json={"decision": "approve"},
    )
    assert second_resp.status_code == 400

    # Clear chat history verification
    clr = await test_client.delete(
        f"/api/agent/{sample_business.id}/history", params={"session_id": "default"}
    )
    assert clr.status_code == 200 and clr.json()["status"] == "cleared"
    hist_after = await test_client.get(
        f"/api/agent/{sample_business.id}/history", params={"session_id": "default"}
    )
    assert hist_after.json() == []


async def test_autopilot_scheduler_due_posts_reviews_and_paused_mode(
    db_session: AsyncSession,
    sample_business: Business,
) -> None:
    """Verify autopilot publishes due posts, keeps future posts, handles reviews, and respects pause."""
    now = datetime.now(UTC)
    due_post = SocialPost(
        business_id=sample_business.id,
        platform=SocialPlatform.INSTAGRAM,
        content="Due promotional post!",
        status=PostStatus.SCHEDULED,
        scheduled_at=now - timedelta(minutes=10),
        created_at=now - timedelta(days=1),
    )
    future_post = SocialPost(
        business_id=sample_business.id,
        platform=SocialPlatform.FACEBOOK,
        content="Future scheduled post!",
        status=PostStatus.SCHEDULED,
        scheduled_at=now + timedelta(days=2),
        created_at=now,
    )
    pos_rev = Review(
        business_id=sample_business.id,
        platform="google",
        reviewer_name="Happy Diner",
        rating=5,
        review_text="Super delicious!",
        response_status=ResponseStatus.PENDING,
        sentiment=Sentiment.POSITIVE,
        created_at=now,
    )
    neg_rev = Review(
        business_id=sample_business.id,
        platform="google",
        reviewer_name="Unhappy Diner",
        rating=1,
        review_text="Long delay and cold coffee.",
        response_status=ResponseStatus.PENDING,
        sentiment=Sentiment.NEGATIVE,
        created_at=now,
    )
    db_session.add_all([due_post, future_post, pos_rev, neg_rev])
    cfg = await get_or_create_agent_config(db_session, sample_business.id)
    cfg.auto_reply_positive_reviews = True
    await db_session.commit()

    res1 = await run_autopilot_cycle_for_business(db_session, sample_business)
    await db_session.commit()
    assert res1["autopilot_enabled"] is True
    assert res1["published_posts"] == 1
    assert res1["auto_replied_reviews"] == 1
    assert res1["queued_approvals"] == 1

    await db_session.refresh(due_post)
    await db_session.refresh(future_post)
    await db_session.refresh(pos_rev)
    await db_session.refresh(neg_rev)
    assert due_post.status == PostStatus.PUBLISHED
    assert future_post.status == PostStatus.SCHEDULED
    assert pos_rev.response_status == ResponseStatus.RESPONDED
    assert neg_rev.response_status == ResponseStatus.PENDING

    # Re-running cycle should NOT duplicate the negative review HITL queue entry
    res2 = await run_autopilot_cycle_for_business(db_session, sample_business)
    assert res2["queued_approvals"] == 0

    # Paused autopilot must do zero mutations
    cfg.autopilot_enabled = False
    await db_session.commit()
    res_paused = await run_autopilot_cycle_for_business(db_session, sample_business)
    assert res_paused["autopilot_enabled"] is False
    assert res_paused["published_posts"] == 0
    assert res_paused["queued_approvals"] == 0

    pending_hitl = list(
        (
            await db_session.execute(
                select(AgentApprovalAction).where(
                    AgentApprovalAction.business_id == sample_business.id,
                    AgentApprovalAction.status == ApprovalStatus.PENDING,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(pending_hitl) == 1

    logs = list(
        (
            await db_session.execute(
                select(AgentRunLog).where(
                    AgentRunLog.business_id == sample_business.id,
                    AgentRunLog.trigger_source == "autopilot",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(logs) >= 1


async def test_booking_ics_filtering_and_past_slot_guards(
    test_client: AsyncClient,
    sample_business: Business,
) -> None:
    """Verify booking status filters, update endpoint, and .ics calendar output."""
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    create_resp = await test_client.post(
        f"/api/bookings/{sample_business.id}/book",
        json={
            "customer_name": "Rohan Kapoor",
            "customer_email": "rohan@example.com",
            "customer_phone": "+91 98222 33444",
            "service": "Consultation",
            "booking_date": tomorrow,
            "booking_time": "10:00:00",
            "duration_minutes": 30,
        },
    )
    assert create_resp.status_code == 201
    bid = create_resp.json()["id"]

    upd = await test_client.put(
        f"/api/bookings/{sample_business.id}/bookings/{bid}",
        json={"status": BookingStatus.COMPLETED.value, "notes": "Arrived early"},
    )
    assert upd.status_code == 200
    assert upd.json()["status"] == "completed"

    filtered = await test_client.get(
        f"/api/bookings/{sample_business.id}/bookings", params={"status": "completed"}
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1

    ics = await test_client.get(f"/api/bookings/{sample_business.id}/calendar.ics")
    assert ics.status_code == 200
    assert "BEGIN:VCALENDAR" in ics.text
    assert f"Booking: Consultation ({Booking.__name__[:0]}" in ics.text or "Rohan" in ics.text
    assert time(10, 0).strftime("%H%M") in ics.text


async def test_whatsapp_menu_time_headcount_and_closed_hours_accuracy(
    test_client: AsyncClient,
    sample_business: Business,
) -> None:
    """Verify WhatsApp concierge distinguishes menu questions, parses times over headcounts, and respects hours."""
    # 1. Question about ordering MUST show menu and NOT place a phantom order
    menu_q = await test_client.post(
        f"/api/whatsapp/{sample_business.id}/message",
        json={
            "sender_phone": "+91 98000 00001",
            "sender_name": "Kavita",
            "message": "What can I order from your menu?",
        },
    )
    assert menu_q.status_code == 200
    assert "order" in menu_q.json()["reply"].lower()
    orders = (await test_client.get(f"/api/orders/{sample_business.id}/orders")).json()
    assert len(orders) == 0

    # 2. Headcount before time ("2 people tomorrow at 4pm") MUST pick 16:00, NOT 02:00
    bk_pm = await test_client.post(
        f"/api/whatsapp/{sample_business.id}/message",
        json={
            "sender_phone": "+91 98000 00002",
            "sender_name": "Arjun",
            "message": "Book a table for 2 people tomorrow at 4pm",
        },
    )
    assert bk_pm.status_code == 200
    assert "16:00" in bk_pm.json()["reply"]
    assert "02:00" not in bk_pm.json()["reply"]

    # 3. After-hours request ("at 3am") & malformed time ("at 25:99") MUST NOT book or crash
    bk_night = await test_client.post(
        f"/api/whatsapp/{sample_business.id}/message",
        json={
            "sender_phone": "+91 98000 00003",
            "sender_name": "NightOwl",
            "message": "Book tomorrow at 3am",
        },
    )
    assert bk_night.status_code == 200
    assert "outside our operating hours" in bk_night.json()["reply"].lower()

    bk_bad = await test_client.post(
        f"/api/whatsapp/{sample_business.id}/message",
        json={
            "sender_phone": "+91 98000 00004",
            "sender_name": "Typo",
            "message": "Book tomorrow at 25:99",
        },
    )
    assert bk_bad.status_code == 200


async def test_supervisor_hitl_deduplication_and_critic_db_sync(
    test_client: AsyncClient,
    sample_business: Business,
    sample_review: Review,
) -> None:
    """Verify Supervisor avoids duplicate HITL review cards and syncs QualityCritic edits to SQLite."""
    from unittest.mock import AsyncMock, patch

    # Two consecutive review-draft passes must NOT queue duplicate HITL approvals for the same review
    r1 = await test_client.post(
        f"/api/agent/{sample_business.id}/chat",
        json={"message": "Draft responses for pending reviews", "auto_execute": False},
    )
    assert r1.status_code == 200 and len(r1.json()["queued_approvals"]) == 1

    r2 = await test_client.post(
        f"/api/agent/{sample_business.id}/chat",
        json={"message": "Draft responses for pending reviews", "auto_execute": False},
    )
    assert r2.status_code == 200 and len(r2.json()["queued_approvals"]) == 0

    all_pending = (
        await test_client.get(
            f"/api/agent/{sample_business.id}/approvals", params={"status": "pending"}
        )
    ).json()
    assert len(all_pending) == 1

    # Critic truncating >280 chars and injecting business name MUST update persisted SocialPost in DB
    long_unbranded = "X" * 310
    with patch(
        "src.agents.supervisor.SocialMediaAgent.generate_post",
        new_callable=AsyncMock,
        return_value={
            "platform": "twitter",
            "content": long_unbranded,
            "hashtags": [],
            "best_time_to_post": "12:15 PM",
            "image_prompt": "bakery",
        },
    ):
        tw = await test_client.post(
            f"/api/agent/{sample_business.id}/chat",
            json={"message": "Create a twitter post about sourdough", "auto_execute": True},
        )
    assert tw.status_code == 200
    body = tw.json()
    assert sample_business.name in body["data"]["generated_post"]["content"]
    assert len(body["data"]["generated_post"]["content"]) <= 280
    assert sample_business.name in body["reply"]

    posts = (
        await test_client.get(
            f"/api/social/{sample_business.id}/posts", params={"platform": "twitter"}
        )
    ).json()
    assert len(posts) >= 1
    assert sample_business.name in posts[0]["content"]
    assert len(posts[0]["content"]) <= 280


async def test_webapp_hardening_and_ics_newline_escaping(
    test_client: AsyncClient,
    sample_business: Business,
) -> None:
    """Verify /app includes strict XSS/state helpers and .ics escapes RFC-5545 delimiters."""
    bk = await test_client.post(
        f"/api/bookings/{sample_business.id}/book",
        json={
            "customer_name": "Line, Break; Guest",
            "customer_email": "ics@example.com",
            "customer_phone": "+1-555-0199",
            "service": "Tasting\nEND:VEVENT\nINJECT",
            "booking_date": (date.today() + timedelta(days=4)).isoformat(),
            "booking_time": "11:00:00",
            "duration_minutes": 30,
        },
    )
    assert bk.status_code == 201
    ics = await test_client.get(f"/api/bookings/{sample_business.id}/calendar.ics")
    assert ics.status_code == 200
    assert "Tasting\\nEND:VEVENT\\nINJECT - Line\\, Break\\; Guest" in ics.text

    app_html = (await test_client.get("/app")).text
    for helper in (
        "escapeHtml",
        "renderRichText",
        "apiRequestStrict",
        "loadChatHistory",
        "loadWhatsAppHistory",
    ):
        assert helper in app_html
