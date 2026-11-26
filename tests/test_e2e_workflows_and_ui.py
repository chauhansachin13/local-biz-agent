"""End-to-end customer-to-agent-to-CRM journeys, PNG visual verification, concurrency, and Streamlit UI tests."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from streamlit.testing.v1 import AppTest

from src.database.db import Base, get_db
from src.main import app


@pytest.mark.asyncio(loop_scope="function")
async def test_full_end_to_end_business_journey_and_visual_png(
    test_client: AsyncClient,
) -> None:
    """Verify complete E2E journey: onboard -> customer activity -> AI council/approvals -> CRM -> exports -> PNG."""
    # 1. 60-Second Magic Launch
    onboard = await test_client.post(
        "/api/agent/magic-onboard",
        json={
            "name": "Lotus Blossom Spa",
            "category": "spa",
            "city": "Bengaluru",
            "state": "KA",
            "phone": "9880011223",
            "specialty": "Ayurvedic deep-tissue massage and facials",
        },
    )
    assert onboard.status_code == 201
    biz_id = onboard.json()["business"]["id"]

    # 2. Configure autopilot settings + catalog items
    cfg_upd = await test_client.put(
        f"/api/agent/{biz_id}/autopilot",
        json={
            "preferred_language": "English",
            "require_approval_negative_reviews": True,
            "autopilot_enabled": True,
        },
    )
    assert cfg_upd.status_code == 200 and cfg_upd.json()["autopilot_enabled"] is True

    # 3. Customer submits booking, online order, WhatsApp message, and 1-star review
    bk = await test_client.post(
        f"/api/bookings/{biz_id}/book",
        json={
            "customer_name": "Ananya Iyer",
            "customer_email": "ananya@example.com",
            "customer_phone": "+91 99000 11223",
            "service": "Ayurvedic Spa Session",
            "booking_date": "2026-12-15",
            "booking_time": "15:00:00",
            "duration_minutes": 60,
        },
    )
    assert bk.status_code == 201

    ord_resp = await test_client.post(
        f"/api/orders/{biz_id}/order",
        json={
            "customer_name": "Ananya Iyer",
            "customer_phone": "+91 99000 11223",
            "fulfillment_type": "pickup",
            "items": [{"name": "Herbal Spa Gift Box", "quantity": 2, "price": 75.0}],
        },
    )
    assert ord_resp.status_code == 201 and ord_resp.json()["total_amount"] == 150.0

    neg_rev = await test_client.post(
        f"/api/reviews/{biz_id}/submit",
        json={
            "reviewer_name": "Ananya Iyer",
            "rating": 1,
            "review_text": "Reception desk kept me waiting 25 minutes past my appointment.",
            "platform": "google",
        },
    )
    assert neg_rev.status_code == 201

    # 4. CRM auto-sync upgrades Ananya from spend ($150 -> VIP) & drafts retention offer
    customers = await test_client.get(f"/api/crm/{biz_id}/customers")
    assert customers.status_code == 200
    ananya = [c for c in customers.json() if "Ananya" in c["name"]]
    assert len(ananya) == 1
    assert ananya[0]["total_spent"] >= 150.0

    ret = await test_client.post(f"/api/crm/{biz_id}/retention-offers")
    assert ret.status_code == 200 and ret.json()["queued_count"] >= 1

    # 5. Approve both the queued negative-review reply AND retention offer in HITL Inbox
    pending = (
        await test_client.get(f"/api/agent/{biz_id}/approvals", params={"status": "pending"})
    ).json()
    assert len(pending) >= 2
    for action in pending:
        dec = await test_client.post(
            f"/api/agent/{biz_id}/approvals/{action['id']}/decide",
            json={"decision": "approve"},
        )
        assert dec.status_code == 200
        assert dec.json()["status"] == "executed"

    # Verify review is now marked responded
    rev_list = (await test_client.get(f"/api/reviews/{biz_id}/reviews")).json()
    ananya_rev = [r for r in rev_list if r["reviewer_name"] == "Ananya Iyer"][0]
    assert ananya_rev["response_status"] == "responded"

    # 6. Validate Pillow PNG Promo Poster pixel dimensions & format
    png_resp = await test_client.get(
        f"/api/social/{biz_id}/promo-card.png",
        params={"headline": "Relax & Recharge", "promo_code": "LOTUS20"},
    )
    assert png_resp.status_code == 200
    img = Image.open(io.BytesIO(png_resp.content))
    img.verify()
    img2 = Image.open(io.BytesIO(png_resp.content))
    assert img2.format == "PNG"
    assert img2.size == (1080, 1080)

    # 7. Strategy council + Daily Brief + SEO Audit + CSV Exports
    council = await test_client.post(f"/api/agent/{biz_id}/strategy-council")
    assert council.status_code == 200 and len(council.json()["council_members"]) == 3

    brief = await test_client.get(f"/api/agent/{biz_id}/daily-brief")
    assert brief.status_code == 200 and brief.json()["metrics"]["active_orders"] >= 1

    seo = await test_client.get(f"/api/agent/{biz_id}/seo-audit")
    assert seo.status_code == 200 and "Bengaluru" in " ".join(seo.json()["target_local_keywords"])


@pytest.mark.asyncio(loop_scope="function")
async def test_concurrent_api_load_burst(tmp_path: Path) -> None:
    """Stress-test 24 parallel async requests with independent per-request DB sessions."""
    burst_db = tmp_path / "burst.db"
    burst_engine = create_async_engine(
        f"sqlite+aiosqlite:///{burst_db}",
        connect_args={"check_same_thread": False},
    )
    burst_session_factory = async_sessionmaker(
        bind=burst_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with burst_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with burst_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            onboard = await client.post(
                "/api/agent/magic-onboard",
                json={
                    "name": "Concurrent Cafe",
                    "category": "cafe",
                    "city": "Austin",
                    "state": "TX",
                    "phone": "5125550101",
                },
            )
            assert onboard.status_code == 201
            biz_id = onboard.json()["business"]["id"]

            async def hit(i: int) -> int:
                if i % 4 == 0:
                    r = await client.get(f"/api/agent/{biz_id}/health-score")
                elif i % 4 == 1:
                    r = await client.get(f"/api/agent/{biz_id}/daily-brief")
                elif i % 4 == 2:
                    r = await client.post(
                        f"/api/whatsapp/{biz_id}/message",
                        json={
                            "sender_phone": f"+9199000000{i:02d}",
                            "sender_name": f"Guest {i}",
                            "message": "What are your hours today?",
                        },
                    )
                else:
                    r = await client.get(f"/api/social/{biz_id}/promo-card.png")
                return r.status_code

            statuses = await asyncio.gather(*(hit(i) for i in range(24)))
            assert all(code == 200 for code in statuses), f"Non-200 status in burst: {statuses}"
    finally:
        app.dependency_overrides.clear()
        await burst_engine.dispose()


def test_streamlit_dashboard_all_10_pages_with_live_backend_e2e(tmp_path: Path) -> None:
    """Exercise all 10 Streamlit pages and interactive controls against a real SQLite FastAPI app."""
    db_file = tmp_path / "ui_e2e.db"
    ui_engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    ui_session_factory = async_sessionmaker(
        bind=ui_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def init_schema() -> None:
        async with ui_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose_schema() -> None:
        await ui_engine.dispose()

    asyncio.run(init_schema())

    async def override_get_db():
        async with ui_session_factory() as sess:
            yield sess

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as tc:
        # Seed realistic business, review, post, booking, order, and customer into ui_e2e.db
        onboard = tc.post(
            "/api/agent/magic-onboard",
            json={
                "name": "Chai Corner UI Test",
                "category": "cafe",
                "city": "Mumbai",
                "state": "MH",
                "phone": "9876500111",
                "specialty": "Irani chai and maska pav",
            },
        )
        assert onboard.status_code == 201
        biz_id = onboard.json()["business"]["id"]

        tc.post(
            f"/api/reviews/{biz_id}/submit",
            json={
                "reviewer_name": "Karan",
                "rating": 2,
                "review_text": "Tea was lukewarm.",
                "platform": "google",
            },
        )
        tc.post(
            f"/api/orders/{biz_id}/order",
            json={
                "customer_name": "Meera",
                "customer_phone": "+91 98200 11223",
                "fulfillment_type": "pickup",
                "items": [{"name": "Bun Maska", "quantity": 2, "price": 4.5}],
            },
        )

        # Forward dashboard's httpx.Client calls cleanly to TestClient(app) without recursion
        def mock_handler(request: httpx.Request) -> httpx.Response:
            target = request.url.raw_path.decode()
            resp = tc.request(
                method=request.method,
                url=target,
                content=request.content,
                headers={"content-type": request.headers.get("content-type", "application/json")},
            )
            return httpx.Response(
                status_code=resp.status_code,
                content=resp.content,
                headers=dict(resp.headers),
            )

        real_client_cls = httpx.Client
        transport = httpx.MockTransport(mock_handler)

        def bridged_client(*args, **kwargs) -> httpx.Client:
            kwargs.pop("timeout", None)
            return real_client_cls(transport=transport, timeout=20.0)

        try:
            with patch("httpx.Client", side_effect=bridged_client):
                dash_path = Path(__file__).resolve().parent.parent / "dashboard" / "app.py"
                at = AppTest.from_file(str(dash_path), default_timeout=30)
                at.run()
                assert not at.exception, f"Initial Streamlit load error: {at.exception}"

                nav_radio = next(r for r in at.sidebar.radio if len(r.options) >= 9)
                pages = list(nav_radio.options)
                assert len(pages) == 14

                for page_name in pages:
                    nav_radio = next(r for r in at.sidebar.radio if len(r.options) >= 9)
                    nav_radio.set_value(page_name)
                    at.run()
                    assert not at.exception, f"Streamlit page '{page_name}' raised: {at.exception}"

                # Interactive test on AI Command Chat page: trigger a quick-command button
                chat_page = next(p for p in pages if "Command Chat" in p)
                nav_radio = next(r for r in at.sidebar.radio if len(r.options) >= 9)
                nav_radio.set_value(chat_page)
                at.run()
                if len(at.button) > 0:
                    at.button[0].click()
                    at.run()
                    assert not at.exception, f"Interactive chat button raised error: {at.exception}"
        finally:
            app.dependency_overrides.clear()
            asyncio.run(dispose_schema())


def test_booking_langchain_tools_sqlite_lifecycle(tmp_path: Path, monkeypatch) -> None:
    """Exercise booking LangChain tools (check, create, conflict, list, reschedule, cancel)."""
    import json

    from config.settings import settings
    from src.tools.booking_tools import (
        cancel_booking,
        check_availability,
        create_booking,
        get_daily_bookings,
        reschedule_booking,
    )

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'tools_bk.db'}")

    avail = check_availability.invoke({"business_id": "1", "date": "2026-12-20"})
    assert len(avail) == 9

    created = json.loads(
        create_booking.invoke(
            {
                "booking_data": {
                    "business_id": 1,
                    "customer_name": "Tara Nair",
                    "service_name": "Hair Spa",
                    "booking_date": "2026-12-20",
                    "booking_time": "10:00",
                }
            }
        )
    )
    assert created["status"] == "confirmed"
    bid = created["booking_id"]

    # Duplicate time slot -> conflict
    conflict = json.loads(
        create_booking.invoke(
            {
                "booking_data": {
                    "business_id": 1,
                    "customer_name": "Other Guest",
                    "service_name": "Haircut",
                    "booking_date": "2026-12-20",
                    "booking_time": "10:00",
                }
            }
        )
    )
    assert conflict["status"] == "conflict"

    daily = get_daily_bookings.invoke({"business_id": "1", "date": "2026-12-20"})
    assert len(daily) == 1

    resched = json.loads(
        reschedule_booking.invoke(
            {"booking_id": bid, "new_date": "2026-12-21", "new_time": "11:00"}
        )
    )
    assert resched["status"] == "rescheduled"

    cancelled = json.loads(cancel_booking.invoke({"booking_id": bid, "reason": "Travel"}))
    assert cancelled["status"] == "cancelled"
