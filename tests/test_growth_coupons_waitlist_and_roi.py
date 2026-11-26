"""Comprehensive functional, boundary, security, and ROI tests for Coupons, Waitlist, FAQs, Broadcasts, and Localization."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from src.models.business import Business

pytestmark = pytest.mark.asyncio(loop_scope="function")


async def test_coupon_creation_boundaries_validation_and_order_checkout(
    test_client: AsyncClient,
    sample_business: Business,
) -> None:
    """Verify strict coupon schema caps, expiry/min/usage checks, and server-side order discount math."""
    biz_id = sample_business.id

    # Boundary rejection: >100% discount
    over_pct = await test_client.post(
        f"/api/growth/{biz_id}/coupons",
        json={
            "code": "BAD150",
            "title": "Invalid over 100%",
            "discount_type": "percent",
            "discount_value": 150.0,
        },
    )
    assert over_pct.status_code == 422

    # Valid percent coupon (min $30, max 1 use to test exhaustion cleanly)
    good_pct = await test_client.post(
        f"/api/growth/{biz_id}/coupons",
        json={
            "code": "save20 ",
            "title": "20% Off Orders $30+",
            "discount_type": "percent",
            "discount_value": 20.0,
            "min_order_amount": 30.0,
            "max_uses": 1,
            "valid_until": (date.today() + timedelta(days=7)).isoformat(),
        },
    )
    assert good_pct.status_code == 201
    assert good_pct.json()["code"] == "SAVE20"
    cid = good_pct.json()["id"]

    # Duplicate code -> 409 Conflict
    dup = await test_client.post(
        f"/api/growth/{biz_id}/coupons",
        json={
            "code": "SAVE20",
            "title": "Duplicate",
            "discount_type": "fixed",
            "discount_value": 5.0,
        },
    )
    assert dup.status_code == 409

    # Fixed coupon exceeding subtotal must cap discount at subtotal (total == 0.0, never negative)
    flat = await test_client.post(
        f"/api/growth/{biz_id}/coupons",
        json={
            "code": "FLAT50",
            "title": "$50 Voucher",
            "discount_type": "fixed",
            "discount_value": 50.0,
            "min_order_amount": 0.0,
        },
    )
    assert flat.status_code == 201
    flat_check = (
        await test_client.post(
            f"/api/growth/{biz_id}/coupons/validate",
            json={"code": "flat50", "subtotal": 12.5},
        )
    ).json()
    assert flat_check["valid"] is True
    assert flat_check["discount_amount"] == 12.5
    assert flat_check["final_total"] == 0.0

    # Expired coupon check
    exp = await test_client.post(
        f"/api/growth/{biz_id}/coupons",
        json={
            "code": "OLD10",
            "title": "Expired Offer",
            "discount_type": "percent",
            "discount_value": 10.0,
            "valid_until": (date.today() - timedelta(days=1)).isoformat(),
        },
    )
    assert exp.status_code == 201
    exp_check = (
        await test_client.post(
            f"/api/growth/{biz_id}/coupons/validate",
            json={"code": "OLD10", "subtotal": 50.0},
        )
    ).json()
    assert exp_check["valid"] is False and "expired" in exp_check["reason"].lower()

    # Order below min_order_amount must fail with 400
    under_min = await test_client.post(
        f"/api/orders/{biz_id}/order",
        json={
            "customer_name": "Nina",
            "customer_phone": "+1-512-555-0111",
            "items": [{"name": "Muffin", "quantity": 1, "price": 10.0}],
            "promo_code": "SAVE20",
        },
    )
    assert under_min.status_code == 400

    # Valid order applies 20% off $40.00 -> subtotal $40, discount $8, total $32, uses_count becomes 1
    ok_order = await test_client.post(
        f"/api/orders/{biz_id}/order",
        json={
            "customer_name": "Nina",
            "customer_phone": "+1-512-555-0111",
            "items": [{"name": "Pastry Box", "quantity": 2, "price": 20.0}],
            "promo_code": "save20",
        },
    )
    assert ok_order.status_code == 201
    od = ok_order.json()
    assert od["subtotal_amount"] == 40.0
    assert od["discount_amount"] == 8.0
    assert od["total_amount"] == 32.0
    assert od["promo_code"] == "SAVE20"

    # Re-using SAVE20 beyond max_uses=1 must be rejected cleanly
    exhausted = await test_client.post(
        f"/api/orders/{biz_id}/order",
        json={
            "customer_name": "Sam",
            "customer_phone": "+1-512-555-0112",
            "items": [{"name": "Pastry Box", "quantity": 2, "price": 20.0}],
            "promo_code": "SAVE20",
        },
    )
    assert exhausted.status_code == 400

    # Pause & delete coupon
    paused = await test_client.patch(
        f"/api/growth/{biz_id}/coupons/{cid}", json={"is_active": False}
    )
    assert paused.status_code == 200 and paused.json()["is_active"] is False
    deleted = await test_client.delete(f"/api/growth/{biz_id}/coupons/{cid}")
    assert deleted.status_code == 200


async def test_waitlist_auto_alert_on_cancellation_and_whatsapp_self_service(
    test_client: AsyncClient,
    sample_business: Business,
) -> None:
    """Verify booking cancellation auto-alerts waitlist and WhatsApp handles cancel/reschedule/FAQs/promos."""
    biz_id = sample_business.id
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    # 1. Active coupon + grounded FAQ setup
    await test_client.post(
        f"/api/growth/{biz_id}/coupons",
        json={
            "code": "VIP15",
            "title": "15% Off Pickups",
            "discount_type": "percent",
            "discount_value": 15.0,
        },
    )
    await test_client.put(
        f"/api/growth/{biz_id}/faqs",
        json={
            "faqs": [
                {
                    "q": "Do you have vegan or gluten-free options?",
                    "a": "Yes! We bake fresh vegan rosemary loaves and gluten-free brownies daily.",
                }
            ]
        },
    )

    # 2. Grounded FAQ & Promo lookup on WhatsApp
    faq_q = await test_client.post(
        f"/api/whatsapp/{biz_id}/message",
        json={
            "sender_phone": "+91 98111 00001",
            "sender_name": "Tara",
            "message": "Do you have any vegan options?",
        },
    )
    assert faq_q.status_code == 200
    assert faq_q.json()["agent_used"] == "FAQKnowledgeAgent"
    assert "rosemary" in faq_q.json()["reply"].lower()

    promo_q = await test_client.post(
        f"/api/whatsapp/{biz_id}/message",
        json={
            "sender_phone": "+91 98111 00001",
            "sender_name": "Tara",
            "message": "Do you have any active promo codes or discounts?",
        },
    )
    assert promo_q.status_code == 200 and "VIP15" in promo_q.json()["reply"]

    # 3. WhatsApp order with promo code applied cleanly
    wa_ord = await test_client.post(
        f"/api/whatsapp/{biz_id}/message",
        json={
            "sender_phone": "+91 98111 00001",
            "sender_name": "Tara",
            "message": "Order 2 Signature Combo code VIP15",
        },
    )
    assert wa_ord.status_code == 200
    assert "VIP15" in wa_ord.json()["reply"]

    # 4. Join Waitlist, then Book via WhatsApp, Reschedule via WhatsApp, then Cancel -> Waitlist Notified
    wl = await test_client.post(
        f"/api/growth/{biz_id}/waitlist",
        json={
            "customer_name": "Rhea Wait",
            "customer_phone": "+91 98222 77777",
            "preferred_date": tomorrow,
            "preferred_time": "14:00",
            "service": "Tasting",
        },
    )
    assert wl.status_code == 201 and wl.json()["status"] == "waiting"

    wa_bk = await test_client.post(
        f"/api/whatsapp/{biz_id}/message",
        json={
            "sender_phone": "+91 98111 00001",
            "sender_name": "Tara",
            "message": "Book tomorrow at 15:00",
        },
    )
    assert wa_bk.status_code == 200
    bk_id = wa_bk.json()["extra"]["booking_id"]

    wa_resch = await test_client.post(
        f"/api/whatsapp/{biz_id}/message",
        json={
            "sender_phone": "+91 98111 00001",
            "sender_name": "Tara",
            "message": f"Reschedule booking #{bk_id} to tomorrow at 16:00",
        },
    )
    assert wa_resch.status_code == 200 and "16:00" in wa_resch.json()["reply"]

    wa_cancel = await test_client.post(
        f"/api/whatsapp/{biz_id}/message",
        json={
            "sender_phone": "+91 98111 00001",
            "sender_name": "Tara",
            "message": f"Cancel booking #{bk_id}",
        },
    )
    assert wa_cancel.status_code == 200 and "cancelled" in wa_cancel.json()["reply"].lower()
    assert wa_cancel.json()["extra"]["waitlist_notified"] == 1

    wl_after = (await test_client.get(f"/api/growth/{biz_id}/waitlist")).json()
    assert wl_after[0]["status"] == "notified"


async def test_broadcast_revenue_roi_supervisor_translate_and_menu_page(
    test_client: AsyncClient,
    sample_business: Business,
) -> None:
    """Verify segmented broadcasts + HITL, localization, exact Revenue ROI, and /site/{id}/menu."""
    biz_id = sample_business.id

    await test_client.post(
        f"/api/growth/{biz_id}/coupons",
        json={
            "code": "LOCAL15",
            "title": "15% Off Pickup",
            "discount_type": "percent",
            "discount_value": 15.0,
        },
    )
    await test_client.post(
        f"/api/orders/{biz_id}/order",
        json={
            "customer_name": "Meera Nair",
            "customer_phone": "+91 98765 54321",
            "items": [{"name": "Sourdough Loaf", "quantity": 4, "price": 10.0}],
            "promo_code": "LOCAL15",
        },
    )

    # Queue VIP broadcast in HITL Inbox -> Approve -> Executes outbound WhatsAppMessage
    bc = await test_client.post(
        f"/api/growth/{biz_id}/broadcast",
        json={
            "segment": "All",
            "topic": "Fresh weekend pastry batch just came out!",
            "promo_code": "LOCAL15",
            "auto_execute": False,
        },
    )
    assert bc.status_code == 200
    assert bc.json()["status"] == "queued_for_approval"
    ap_id = bc.json()["approval_action_id"]

    dec = await test_client.post(
        f"/api/agent/{biz_id}/approvals/{ap_id}/decide", json={"decision": "approve"}
    )
    assert dec.status_code == 200 and dec.json()["status"] == "executed"

    # Revenue ROI math check ($40 subtotal, 15% = $6 discount, net = $34.00)
    roi = (await test_client.get(f"/api/growth/{biz_id}/revenue-analytics")).json()
    assert roi["gross_order_revenue"] == 40.0
    assert roi["total_discounts_given"] == 6.0
    assert roi["net_order_revenue"] == 34.0
    assert roi["top_ordered_items"][0]["name"] == "Sourdough Loaf"
    assert roi["top_ordered_items"][0]["units_sold"] == 4

    # Supervisor chat checks revenue ROI cleanly
    chat_roi = await test_client.post(
        f"/api/agent/{biz_id}/chat", json={"message": "Show our revenue ROI and promo usage"}
    )
    assert chat_roi.status_code == 200
    assert "revenue_roi" in chat_roi.json()["plan"]
    assert "$34.00" in chat_roi.json()["reply"]

    # FAQ Suggest & Translation
    faq_sug = await test_client.post(f"/api/growth/{biz_id}/faqs/suggest?apply=true")
    assert faq_sug.status_code == 200 and len(faq_sug.json()["faqs"]) >= 4

    tr = await test_client.post(
        f"/api/growth/{biz_id}/translate",
        json={"text": "15% off today with LOCAL15!", "target_language": "Hindi"},
    )
    assert tr.status_code == 200 and "LOCAL15" in tr.json()["translated_text"]

    # Printable Menu (/site/{id}/menu), Storefront (/site/{id}), and /app Web UI
    menu_html = (await test_client.get(f"/site/{biz_id}/menu")).text
    assert "LOCAL15" in menu_html and "Digital Menu" in menu_html
    site_html = (await test_client.get(f"/site/{biz_id}")).text
    assert "Join the Waitlist" in site_html and "checkPromoCode" in site_html
    app_html = (await test_client.get("/app")).text
    assert "tab-growth" in app_html and "loadGrowth" in app_html


async def test_concurrent_crm_sync_and_roi_zero_duplicates(tmp_path) -> None:
    """Verify parallel calls to CRM sync and revenue analytics never create duplicate CustomerProfile rows."""
    import asyncio

    from httpx import ASGITransport
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.database.db import Base, get_db
    from src.main import app

    db_file = tmp_path / "crm_race.db"
    race_engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    race_factory = async_sessionmaker(bind=race_engine, class_=AsyncSession, expire_on_commit=False)
    async with race_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_db():
        async with race_factory() as sess:
            yield sess

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            onb = await client.post(
                "/api/agent/magic-onboard",
                json={"name": "Race Cafe", "category": "cafe", "city": "Pune"},
            )
            assert onb.status_code == 201
            biz_id = onb.json()["business"]["id"]

            await client.post(
                f"/api/orders/{biz_id}/order",
                json={
                    "customer_name": "Kiran Rao",
                    "customer_phone": "+91-98111-22334",
                    "items": [{"name": "Masala Chai", "quantity": 2, "price": 5.0}],
                },
            )
            await client.post(
                f"/api/reviews/{biz_id}/submit",
                json={"reviewer_name": "Kiran Rao", "rating": 5, "review_text": "Best chai!"},
            )

            async def call_sync(i: int):
                if i % 2 == 0:
                    return await client.get(f"/api/crm/{biz_id}/customers")
                return await client.get(f"/api/growth/{biz_id}/revenue-analytics")

            resps = await asyncio.gather(*(call_sync(i) for i in range(16)))
            assert all(r.status_code == 200 for r in resps)

            final_crm = (await client.get(f"/api/crm/{biz_id}/customers")).json()
            assert len(final_crm) == 1
            assert final_crm[0]["name"] == "Kiran Rao"
    finally:
        app.dependency_overrides.clear()
        await race_engine.dispose()
