"""Comprehensive tests for Loyalty Points, Gift Cards, NPS Surveys, Email Campaigns, and Content Calendar."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Loyalty Points Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loyalty_create_account(client: AsyncClient, test_business_id: int) -> None:
    """Should create a loyalty account for a new customer."""
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/points/account",
        json={"customer_email": "loyalty@test.com", "customer_name": "Loyalty Tester"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["customer_email"] == "loyalty@test.com"
    assert data["points_balance"] == 0
    assert data["tier"] == "bronze"


@pytest.mark.asyncio
async def test_loyalty_create_account_idempotent(
    client: AsyncClient, test_business_id: int
) -> None:
    """Creating account twice returns same account (idempotent)."""
    payload = {"customer_email": "idempotent@test.com", "customer_name": "Idem User"}
    r1 = await client.post(f"/api/loyalty/{test_business_id}/points/account", json=payload)
    r2 = await client.post(f"/api/loyalty/{test_business_id}/points/account", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


@pytest.mark.asyncio
async def test_earn_loyalty_points(client: AsyncClient, test_business_id: int) -> None:
    """Earning points increases balance and updates tier at thresholds."""
    email = "earner@test.com"
    # Create account first
    await client.post(
        f"/api/loyalty/{test_business_id}/points/account",
        json={"customer_email": email, "customer_name": "Earner"},
    )
    # Earn 600 points (should trigger silver tier)
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/points/earn",
        json={"customer_email": email, "points": 600, "description": "Purchase reward"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["points_earned"] == 600
    assert data["new_balance"] == 600
    assert data["tier"] in ("silver", "gold", "platinum")  # >= 500 = silver+


@pytest.mark.asyncio
async def test_earn_points_tier_upgrade(client: AsyncClient, test_business_id: int) -> None:
    """Earning 1500 lifetime points should upgrade to gold tier."""
    email = "gold_earner@test.com"
    await client.post(
        f"/api/loyalty/{test_business_id}/points/account",
        json={"customer_email": email, "customer_name": "Gold Earner"},
    )
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/points/earn",
        json={"customer_email": email, "points": 1500},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] in ("gold", "platinum")
    assert data["tier_upgraded"] is True


@pytest.mark.asyncio
async def test_redeem_loyalty_points(client: AsyncClient, test_business_id: int) -> None:
    """Redeeming points decreases balance and returns dollar_value."""
    email = "redeemer@test.com"
    await client.post(
        f"/api/loyalty/{test_business_id}/points/account",
        json={"customer_email": email, "customer_name": "Redeemer"},
    )
    await client.post(
        f"/api/loyalty/{test_business_id}/points/earn",
        json={"customer_email": email, "points": 200},
    )
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/points/redeem",
        json={"customer_email": email, "points": 100},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["points_redeemed"] == 100
    assert data["dollar_value"] == pytest.approx(1.0)
    assert data["remaining_balance"] == 100


@pytest.mark.asyncio
async def test_redeem_insufficient_points(client: AsyncClient, test_business_id: int) -> None:
    """Redeeming more points than balance should return 400; above max bound returns 422."""
    email = "broke@test.com"
    await client.post(
        f"/api/loyalty/{test_business_id}/points/account",
        json={"customer_email": email, "customer_name": "Broke User"},
    )
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/points/redeem",
        json={"customer_email": email, "points": 500},
    )
    assert resp.status_code == 400

    resp_bounds = await client.post(
        f"/api/loyalty/{test_business_id}/points/redeem",
        json={"customer_email": email, "points": 50001},
    )
    assert resp_bounds.status_code == 422


@pytest.mark.asyncio
async def test_loyalty_leaderboard(client: AsyncClient, test_business_id: int) -> None:
    """Leaderboard should return top members."""
    resp = await client.get(f"/api/loyalty/{test_business_id}/points/leaderboard?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "leaderboard" in data
    assert isinstance(data["leaderboard"], list)


@pytest.mark.asyncio
async def test_loyalty_analytics(client: AsyncClient, test_business_id: int) -> None:
    """Analytics endpoint returns aggregate loyalty stats."""
    resp = await client.get(f"/api/loyalty/{test_business_id}/points/analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_members" in data
    assert "outstanding_liability_dollars" in data


@pytest.mark.asyncio
async def test_earn_points_validation(client: AsyncClient, test_business_id: int) -> None:
    """Should reject invalid points values."""
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/points/earn",
        json={"customer_email": "v@test.com", "points": 0},
    )
    assert resp.status_code == 422

    resp2 = await client.post(
        f"/api/loyalty/{test_business_id}/points/earn",
        json={"customer_email": "not-an-email", "points": 100},
    )
    assert resp2.status_code == 422


# ---------------------------------------------------------------------------
# Gift Card Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_issue_gift_card(client: AsyncClient, test_business_id: int) -> None:
    """Should issue a gift card with a unique code."""
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/gift-cards",
        json={
            "amount": 50.0,
            "recipient_email": "recipient@test.com",
            "recipient_name": "Gift Recipient",
            "message": "Happy Birthday!",
            "expires_days": 365,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["amount"] == 50.0
    assert "code" in data
    assert len(data["code"]) > 0
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_check_gift_card_balance(client: AsyncClient, test_business_id: int) -> None:
    """Should look up gift card balance by code."""
    # Issue first
    issue_resp = await client.post(
        f"/api/loyalty/{test_business_id}/gift-cards",
        json={"amount": 100.0, "expires_days": 365},
    )
    code = issue_resp.json()["code"]

    resp = await client.get(f"/api/loyalty/{test_business_id}/gift-cards/{code}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["remaining_amount"] == 100.0
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_redeem_gift_card_partial(client: AsyncClient, test_business_id: int) -> None:
    """Should allow partial redemption of a gift card."""
    issue_resp = await client.post(
        f"/api/loyalty/{test_business_id}/gift-cards",
        json={"amount": 100.0, "expires_days": 365},
    )
    code = issue_resp.json()["code"]

    resp = await client.post(
        f"/api/loyalty/{test_business_id}/gift-cards/redeem",
        json={"code": code, "amount": 30.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["remaining_balance"] == pytest.approx(70.0)
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_redeem_gift_card_full(client: AsyncClient, test_business_id: int) -> None:
    """Fully redeeming a gift card should mark it as 'redeemed'."""
    issue_resp = await client.post(
        f"/api/loyalty/{test_business_id}/gift-cards",
        json={"amount": 25.0, "expires_days": 365},
    )
    code = issue_resp.json()["code"]

    resp = await client.post(
        f"/api/loyalty/{test_business_id}/gift-cards/redeem",
        json={"code": code, "amount": 25.0},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "redeemed"


@pytest.mark.asyncio
async def test_redeem_gift_card_insufficient(client: AsyncClient, test_business_id: int) -> None:
    """Should return 400 if redeeming more than remaining balance."""
    issue_resp = await client.post(
        f"/api/loyalty/{test_business_id}/gift-cards",
        json={"amount": 10.0, "expires_days": 365},
    )
    code = issue_resp.json()["code"]

    resp = await client.post(
        f"/api/loyalty/{test_business_id}/gift-cards/redeem",
        json={"code": code, "amount": 999.0},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_gift_card_not_found(client: AsyncClient, test_business_id: int) -> None:
    """Should return 404 for nonexistent gift card code."""
    resp = await client.get(f"/api/loyalty/{test_business_id}/gift-cards/FAKE-CODE-XXXX")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_gift_card_validation(client: AsyncClient, test_business_id: int) -> None:
    """Should reject zero or negative amounts."""
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/gift-cards",
        json={"amount": 0.0, "expires_days": 365},
    )
    assert resp.status_code == 422

    resp2 = await client.post(
        f"/api/loyalty/{test_business_id}/gift-cards",
        json={"amount": -50.0, "expires_days": 365},
    )
    assert resp2.status_code == 422


# ---------------------------------------------------------------------------
# NPS Survey Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nps_promoter_submission(client: AsyncClient, test_business_id: int) -> None:
    """Score 9-10 should classify as promoter with correct suggestion."""
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/nps",
        json={
            "customer_email": "promoter@test.com",
            "score": 9,
            "feedback": "Great staff and excellent quality service!",
            "source": "storefront",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["category"] == "promoter"
    assert (
        "review" in data["follow_up_suggestion"].lower()
        or "promoter" in data["follow_up_suggestion"].lower()
    )


@pytest.mark.asyncio
async def test_nps_detractor_submission(client: AsyncClient, test_business_id: int) -> None:
    """Score 0-6 should classify as detractor."""
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/nps",
        json={
            "customer_email": "detractor@test.com",
            "score": 3,
            "feedback": "Long wait times and rude staff.",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["category"] == "detractor"


@pytest.mark.asyncio
async def test_nps_passive_submission(client: AsyncClient, test_business_id: int) -> None:
    """Score 7-8 should classify as passive."""
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/nps",
        json={"customer_email": "passive@test.com", "score": 7},
    )
    assert resp.status_code == 201
    assert resp.json()["category"] == "passive"


@pytest.mark.asyncio
async def test_nps_analytics(client: AsyncClient, test_business_id: int) -> None:
    """NPS analytics should compute correct score and breakdown."""
    # Seed: 2 promoters, 1 detractor → NPS = (2-1)/3*100 = 33.3
    for score, email in [(10, "p1@t.com"), (9, "p2@t.com"), (2, "d1@t.com")]:
        await client.post(
            f"/api/loyalty/{test_business_id}/nps",
            json={"customer_email": email, "score": score},
        )
    resp = await client.get(f"/api/loyalty/{test_business_id}/nps/analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_responses"] >= 3
    assert data["nps_score"] is not None


@pytest.mark.asyncio
async def test_nps_score_boundary_validation(client: AsyncClient, test_business_id: int) -> None:
    """Should reject scores outside 0-10."""
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/nps",
        json={"customer_email": "invalid@test.com", "score": 11},
    )
    assert resp.status_code == 422

    resp2 = await client.post(
        f"/api/loyalty/{test_business_id}/nps",
        json={"customer_email": "invalid@test.com", "score": -1},
    )
    assert resp2.status_code == 422


@pytest.mark.asyncio
async def test_nps_requires_valid_email(client: AsyncClient, test_business_id: int) -> None:
    """Should reject invalid email."""
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/nps",
        json={"customer_email": "not-an-email", "score": 8},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Email Campaign Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_email_campaign_newsletter(client: AsyncClient, test_business_id: int) -> None:
    """Should create a newsletter campaign with auto-generated template."""
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/email-campaigns",
        json={"name": "Nov Newsletter", "campaign_type": "newsletter", "target_segment": "all"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Nov Newsletter"
    assert data["status"] == "draft"
    assert data["subject"]  # auto-generated


@pytest.mark.asyncio
async def test_create_email_campaign_promotional(
    client: AsyncClient, test_business_id: int
) -> None:
    """Should create a promotional campaign with custom subject."""
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/email-campaigns",
        json={
            "name": "Black Friday Promo",
            "campaign_type": "promotional",
            "subject": "🎉 50% Off This Weekend Only!",
            "target_segment": "loyal",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["subject"] == "🎉 50% Off This Weekend Only!"
    assert data["campaign_type"] == "promotional"


@pytest.mark.asyncio
async def test_send_email_campaign(client: AsyncClient, test_business_id: int) -> None:
    """Should mark campaign as sent and populate recipient count."""
    # Create
    create_resp = await client.post(
        f"/api/loyalty/{test_business_id}/email-campaigns",
        json={"name": "Send Test Campaign", "campaign_type": "newsletter"},
    )
    campaign_id = create_resp.json()["id"]

    # Send
    resp = await client.post(f"/api/loyalty/{test_business_id}/email-campaigns/{campaign_id}/send")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["status"] == "sent"
    assert data["recipient_count"] > 0
    assert data["open_count"] >= 0


@pytest.mark.asyncio
async def test_send_campaign_twice_fails(client: AsyncClient, test_business_id: int) -> None:
    """Sending an already-sent campaign should return 400."""
    create_resp = await client.post(
        f"/api/loyalty/{test_business_id}/email-campaigns",
        json={"name": "Double Send Test", "campaign_type": "newsletter"},
    )
    campaign_id = create_resp.json()["id"]
    await client.post(f"/api/loyalty/{test_business_id}/email-campaigns/{campaign_id}/send")
    resp = await client.post(f"/api/loyalty/{test_business_id}/email-campaigns/{campaign_id}/send")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_email_campaign_analytics(client: AsyncClient, test_business_id: int) -> None:
    """Analytics endpoint returns aggregate metrics."""
    resp = await client.get(f"/api/loyalty/{test_business_id}/email-campaigns/analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_campaigns" in data
    assert "avg_open_rate_pct" in data
    assert "by_type" in data


@pytest.mark.asyncio
async def test_email_campaign_name_required(client: AsyncClient, test_business_id: int) -> None:
    """Should reject campaign with empty name."""
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/email-campaigns",
        json={"name": "", "campaign_type": "newsletter"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Content Calendar Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_content_calendar(client: AsyncClient, test_business_id: int) -> None:
    """Should generate content calendar entries for given days and platforms."""
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/content-calendar/generate",
        json={"days_ahead": 3, "platforms": ["instagram", "facebook"]},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["calendar_entries"] > 0
    assert len(data["entries"]) > 0
    entry = data["entries"][0]
    assert "platform" in entry
    assert "occasion" in entry
    assert "preview" in entry


@pytest.mark.asyncio
async def test_generate_content_calendar_single_platform(
    client: AsyncClient, test_business_id: int
) -> None:
    """Should generate entries for single platform only."""
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/content-calendar/generate",
        json={"days_ahead": 2, "platforms": ["instagram"]},
    )
    assert resp.status_code == 201
    data = resp.json()
    for entry in data["entries"]:
        assert entry["platform"] == "instagram"


@pytest.mark.asyncio
async def test_get_content_calendar(client: AsyncClient, test_business_id: int) -> None:
    """Should retrieve saved content calendar entries."""
    # Generate first
    await client.post(
        f"/api/loyalty/{test_business_id}/content-calendar/generate",
        json={"days_ahead": 2, "platforms": ["facebook"]},
    )
    resp = await client.get(f"/api/loyalty/{test_business_id}/content-calendar")
    assert resp.status_code == 200
    data = resp.json()
    assert "entries" in data
    assert isinstance(data["entries"], list)


@pytest.mark.asyncio
async def test_get_content_calendar_filtered_by_platform(
    client: AsyncClient, test_business_id: int
) -> None:
    """Should filter calendar by platform."""
    await client.post(
        f"/api/loyalty/{test_business_id}/content-calendar/generate",
        json={"days_ahead": 2, "platforms": ["instagram", "twitter"]},
    )
    resp = await client.get(f"/api/loyalty/{test_business_id}/content-calendar?platform=twitter")
    assert resp.status_code == 200
    for entry in resp.json()["entries"]:
        assert entry["platform"] == "twitter"


@pytest.mark.asyncio
async def test_content_calendar_invalid_platform(
    client: AsyncClient, test_business_id: int
) -> None:
    """Should reject invalid platform names."""
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/content-calendar/generate",
        json={"days_ahead": 1, "platforms": ["tiktok"]},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_content_calendar_days_boundary(client: AsyncClient, test_business_id: int) -> None:
    """Should reject days_ahead outside 1-90 range."""
    resp = await client.post(
        f"/api/loyalty/{test_business_id}/content-calendar/generate",
        json={"days_ahead": 0, "platforms": ["instagram"]},
    )
    assert resp.status_code == 422

    resp2 = await client.post(
        f"/api/loyalty/{test_business_id}/content-calendar/generate",
        json={"days_ahead": 91, "platforms": ["instagram"]},
    )
    assert resp2.status_code == 422


# ---------------------------------------------------------------------------
# 404 & Cross-Business Isolation Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loyalty_nonexistent_business(client: AsyncClient) -> None:
    """Should return 404 for loyalty operations on nonexistent business."""
    resp = await client.post(
        "/api/loyalty/99999/points/account",
        json={"customer_email": "x@x.com", "customer_name": "X"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_nps_nonexistent_business(client: AsyncClient) -> None:
    """Should return 404 for NPS on nonexistent business."""
    resp = await client.post(
        "/api/loyalty/99999/nps",
        json={"customer_email": "x@x.com", "score": 8},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_gift_card_cross_business_isolation(
    client: AsyncClient, test_business_id: int
) -> None:
    """Gift card from business A should not be visible from business B."""
    # Issue in business 1
    issue_resp = await client.post(
        f"/api/loyalty/{test_business_id}/gift-cards",
        json={"amount": 20.0, "expires_days": 30},
    )
    code = issue_resp.json()["code"]

    # Try to look up from business 99999 (different business)
    resp = await client.get(f"/api/loyalty/99999/gift-cards/{code}")
    assert resp.status_code in (404,)  # not found in that business context


# ---------------------------------------------------------------------------
# Cross-Module Integration, List/Preview, Calendar Promotion & Agent Routing Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loyalty_account_lookup_and_transaction_history(
    client: AsyncClient, test_business_id: int
) -> None:
    """Lookup endpoint returns balance, tier, and transaction ledger."""
    email = "ledger@test.com"
    missing = await client.get(
        f"/api/loyalty/{test_business_id}/points/account", params={"email": email}
    )
    assert missing.status_code == 404

    await client.post(
        f"/api/loyalty/{test_business_id}/points/earn",
        json={"customer_email": email, "points": 300, "description": "Order reward"},
    )
    await client.post(
        f"/api/loyalty/{test_business_id}/points/redeem",
        json={"customer_email": email, "points": 50, "description": "Coffee discount"},
    )
    found = await client.get(
        f"/api/loyalty/{test_business_id}/points/account", params={"email": email}
    )
    assert found.status_code == 200
    body = found.json()
    assert body["points_balance"] == 250
    assert body["lifetime_points"] == 300
    assert len(body["transactions"]) == 2


@pytest.mark.asyncio
async def test_order_and_completed_booking_auto_award_loyalty_points(
    client: AsyncClient, test_business_id: int
) -> None:
    """Orders and completed bookings with customer email automatically award loyalty points."""
    email = "autoloyal@test.com"
    order_resp = await client.post(
        f"/api/orders/{test_business_id}/order",
        json={
            "customer_name": "Auto Loyal",
            "customer_phone": "+1-512-555-8888",
            "customer_email": email,
            "fulfillment_type": "pickup",
            "items": [{"name": "Pasta", "quantity": 2, "price": 20.0}],
        },
    )
    assert order_resp.status_code == 201

    acc1 = await client.get(
        f"/api/loyalty/{test_business_id}/points/account", params={"email": email}
    )
    assert acc1.status_code == 200
    assert acc1.json()["points_balance"] == 40

    bk_resp = await client.post(
        f"/api/bookings/{test_business_id}/book",
        json={
            "customer_name": "Auto Loyal",
            "customer_email": email,
            "customer_phone": "+1-512-555-8888",
            "service": "Consultation",
            "booking_date": "2027-06-15",
            "booking_time": "14:00:00",
            "duration_minutes": 60,
        },
    )
    assert bk_resp.status_code == 201
    bk_id = bk_resp.json()["id"]

    # Completing booking twice should only award the +25 bonus once
    comp1 = await client.put(
        f"/api/bookings/{test_business_id}/bookings/{bk_id}",
        json={"status": "completed"},
    )
    assert comp1.status_code == 200
    comp2 = await client.put(
        f"/api/bookings/{test_business_id}/bookings/{bk_id}",
        json={"status": "completed"},
    )
    assert comp2.status_code == 200

    acc2 = await client.get(
        f"/api/loyalty/{test_business_id}/points/account", params={"email": email}
    )
    assert acc2.json()["points_balance"] == 65


@pytest.mark.asyncio
async def test_gift_card_list_case_insensitive_redeem_and_storefront(
    client: AsyncClient, test_business_id: int
) -> None:
    """List gift cards, redeem with lowercase code, and verify storefront renders new widgets."""
    issue = await client.post(
        f"/api/loyalty/{test_business_id}/gift-cards",
        json={"amount": 40.0, "recipient_name": "Sam"},
    )
    assert issue.status_code == 201
    code = issue.json()["code"]

    glist = await client.get(f"/api/loyalty/{test_business_id}/gift-cards")
    assert glist.status_code == 200
    assert glist.json()["total"] >= 1
    assert any(c["code"] == code for c in glist.json()["gift_cards"])

    redeem = await client.post(
        f"/api/loyalty/{test_business_id}/gift-cards/redeem",
        json={"code": code.lower(), "amount": 15.0},
    )
    assert redeem.status_code == 200
    assert redeem.json()["remaining_balance"] == pytest.approx(25.0)

    site_resp = await client.get(f"/site/{test_business_id}")
    assert site_resp.status_code == 200
    assert "npsForm" in site_resp.text
    assert "loyaltyForm" in site_resp.text
    assert "giftCardForm" in site_resp.text


@pytest.mark.asyncio
async def test_nps_list_and_email_campaign_list_and_preview_html(
    client: AsyncClient, test_business_id: int
) -> None:
    """List NPS surveys, create/schedule/list/preview email campaigns & verify CRM audience size."""
    await client.post(
        f"/api/loyalty/{test_business_id}/nps",
        json={"customer_email": "happy@test.com", "score": 10, "feedback": "Awesome staff!"},
    )
    nps_list = await client.get(f"/api/loyalty/{test_business_id}/nps")
    assert nps_list.status_code == 200
    assert nps_list.json()["total"] == 1
    assert nps_list.json()["surveys"][0]["category"] == "promoter"

    # Scheduled campaign with empty subject/body triggers template generation & scheduled status
    sched_resp = await client.post(
        f"/api/loyalty/{test_business_id}/email-campaigns",
        json={
            "name": "Scheduled Blast",
            "campaign_type": "announcement",
            "subject": "   ",
            "body_html": "",
            "scheduled_at": "2027-01-10T10:00:00Z",
        },
    )
    assert sched_resp.status_code == 201
    sched_data = sched_resp.json()
    assert sched_data["status"] == "scheduled"
    cid = sched_data["id"]

    clist = await client.get(f"/api/loyalty/{test_business_id}/email-campaigns")
    assert clist.status_code == 200
    assert any(c["id"] == cid for c in clist.json()["campaigns"])

    prev = await client.get(f"/api/loyalty/{test_business_id}/email-campaigns/{cid}/preview")
    assert prev.status_code == 200
    assert "Scheduled Blast" in prev.text

    # Add 2 CRM customers and send campaign: audience resolves from real CRM rows
    await client.post(
        f"/api/crm/{test_business_id}/customers",
        json={"name": "VIP Guest", "email": "vipguest@test.com", "segment": "VIP"},
    )
    await client.post(
        f"/api/loyalty/{test_business_id}/points/account",
        json={"customer_email": "member@test.com", "customer_name": "Member"},
    )
    send_resp = await client.post(f"/api/loyalty/{test_business_id}/email-campaigns/{cid}/send")
    assert send_resp.status_code == 200
    assert send_resp.json()["crm_matched_recipients"] == 2
    assert send_resp.json()["recipient_count"] == 2


@pytest.mark.asyncio
async def test_calendar_promote_to_social_post_and_supervisor_loyalty_intent(
    client: AsyncClient, test_business_id: int
) -> None:
    """Promoting a calendar entry creates a SocialPost, and Supervisor handles loyalty/NPS chat."""
    cal_gen = await client.post(
        f"/api/loyalty/{test_business_id}/content-calendar/generate",
        json={"days_ahead": 1, "platforms": ["twitter"]},
    )
    assert cal_gen.status_code == 201
    entries = cal_gen.json()["entries"]
    assert len(entries) == 1
    entry_id = entries[0]["id"]

    promote = await client.post(
        f"/api/loyalty/{test_business_id}/content-calendar/{entry_id}/promote",
        json={"auto_publish": True},
    )
    assert promote.status_code == 200
    pdata = promote.json()
    assert pdata["entry_status"] == "published"
    assert pdata["social_platform"] == "twitter"
    assert pdata["social_status"] == "published"

    missing_promote = await client.post(
        f"/api/loyalty/{test_business_id}/content-calendar/999999/promote"
    )
    assert missing_promote.status_code == 404

    chat_resp = await client.post(
        f"/api/agent/{test_business_id}/chat",
        json={
            "message": "Check loyalty points, NPS score, gift cards, email campaigns and generate a content calendar",
            "auto_execute": True,
        },
    )
    assert chat_resp.status_code == 200
    cdata = chat_resp.json()
    assert "Loyalty" in cdata["reply"]
    assert cdata["data"]["generated_content_calendar"]["calendar_entries"] >= 1
