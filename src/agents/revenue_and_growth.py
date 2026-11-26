"""Revenue ROI engine, promo coupon validation, grounded FAQ concierge, waitlist alerts, and broadcasts."""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.crm_and_competitors import sync_customers_from_activity
from src.agents.llm_client import generate_text_with_llm
from src.models.agent_models import (
    AgentApprovalAction,
    AgentRunLog,
    ApprovalStatus,
    BusinessAgentConfig,
    OrderRequest,
    OrderStatus,
    RiskLevel,
    WhatsAppMessage,
)
from src.models.booking import Booking, BookingStatus
from src.models.business import Business
from src.models.growth_models import (
    CouponOffer,
    DiscountType,
    WaitlistEntry,
    WaitlistStatus,
)
from src.models.review import Review

_STOPWORDS = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "am",
    "do",
    "does",
    "did",
    "you",
    "your",
    "we",
    "our",
    "they",
    "what",
    "where",
    "when",
    "which",
    "how",
    "can",
    "could",
    "would",
    "have",
    "has",
    "with",
    "for",
    "from",
    "in",
    "on",
    "at",
    "to",
    "of",
    "and",
    "or",
    "any",
    "there",
    "please",
    "about",
    "hi",
    "hello",
}


async def validate_and_compute_discount(
    db: AsyncSession,
    business_id: int,
    code: str,
    subtotal: float,
    *,
    increment_use: bool = False,
) -> dict[str, Any]:
    """Validate a promo code against rules and calculate exact discount amount."""
    norm_code = (code or "").strip().upper().replace(" ", "")
    subtotal_clean = round(max(0.0, float(subtotal)), 2)

    if not norm_code:
        return {
            "valid": False,
            "code": norm_code,
            "subtotal": subtotal_clean,
            "discount_amount": 0.0,
            "final_total": subtotal_clean,
            "reason": "Promo code cannot be empty.",
            "coupon": None,
        }

    stmt = select(CouponOffer).where(
        CouponOffer.business_id == business_id,
        CouponOffer.code == norm_code,
    )
    coupon = (await db.execute(stmt)).scalar_one_or_none()
    if coupon is None:
        return {
            "valid": False,
            "code": norm_code,
            "subtotal": subtotal_clean,
            "discount_amount": 0.0,
            "final_total": subtotal_clean,
            "reason": f"Promo code '{norm_code}' does not exist for this business.",
            "coupon": None,
        }
    if not coupon.is_active:
        return {
            "valid": False,
            "code": norm_code,
            "subtotal": subtotal_clean,
            "discount_amount": 0.0,
            "final_total": subtotal_clean,
            "reason": f"Promo code '{norm_code}' is currently paused.",
            "coupon": coupon,
        }
    if coupon.valid_until is not None and coupon.valid_until < date.today():
        return {
            "valid": False,
            "code": norm_code,
            "subtotal": subtotal_clean,
            "discount_amount": 0.0,
            "final_total": subtotal_clean,
            "reason": f"Promo code '{norm_code}' expired on {coupon.valid_until.isoformat()}.",
            "coupon": coupon,
        }
    if coupon.uses_count >= coupon.max_uses:
        return {
            "valid": False,
            "code": norm_code,
            "subtotal": subtotal_clean,
            "discount_amount": 0.0,
            "final_total": subtotal_clean,
            "reason": f"Promo code '{norm_code}' has reached its maximum redemption limit.",
            "coupon": coupon,
        }
    if subtotal_clean < float(coupon.min_order_amount):
        return {
            "valid": False,
            "code": norm_code,
            "subtotal": subtotal_clean,
            "discount_amount": 0.0,
            "final_total": subtotal_clean,
            "reason": (
                f"Promo code '{norm_code}' requires a minimum order of "
                f"${float(coupon.min_order_amount):.2f}."
            ),
            "coupon": coupon,
        }

    if coupon.discount_type == DiscountType.PERCENT:
        raw_discount = subtotal_clean * (float(coupon.discount_value) / 100.0)
    else:
        raw_discount = float(coupon.discount_value)

    discount = round(min(subtotal_clean, max(0.0, raw_discount)), 2)
    final_total = round(max(0.0, subtotal_clean - discount), 2)

    if increment_use:
        coupon.uses_count += 1
        await db.flush()

    desc = (
        f"{int(coupon.discount_value)}% off"
        if coupon.discount_type == DiscountType.PERCENT
        else f"${float(coupon.discount_value):.2f} off"
    )
    return {
        "valid": True,
        "code": norm_code,
        "subtotal": subtotal_clean,
        "discount_amount": discount,
        "final_total": final_total,
        "reason": f"Applied '{norm_code}' ({desc}) — saved ${discount:.2f}!",
        "coupon": coupon,
    }


async def answer_from_knowledge_base(
    db: AsyncSession,
    business: Business,
    cfg: BusinessAgentConfig,
    query: str,
) -> tuple[str | None, str]:
    """Answer customer inquiries accurately using active coupons, FAQs, and catalog prices."""
    low = query.lower().strip()
    q_tokens = [t for t in re.findall(r"[a-z0-9]+", low) if len(t) >= 3 and t not in _STOPWORDS]

    # 1. Active promo/discount lookup
    if any(w in low for w in ("coupon", "promo", "discount", "offer", "deal", "voucher")):
        coupons = list(
            (
                await db.execute(
                    select(CouponOffer).where(
                        CouponOffer.business_id == business.id,
                        CouponOffer.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        today = date.today()
        live = [
            c
            for c in coupons
            if (c.valid_until is None or c.valid_until >= today) and c.uses_count < c.max_uses
        ]
        if live:
            lines = [
                f"- Use **`{c.code}`**: {c.title} ("
                f"{f'{int(c.discount_value)}% off' if c.discount_type == DiscountType.PERCENT else f'${c.discount_value:.2f} off'}"
                + (f", min ${c.min_order_amount:.2f}" if c.min_order_amount > 0 else "")
                + ")"
                for c in live[:4]
            ]
            return (
                f"Here are active offers at **{business.name}**:\n"
                + "\n".join(lines)
                + f"\n\nApply any code at `/site/{business.id}` checkout or on WhatsApp!",
                "PromoConciergeAgent",
            )

    # 2. Grounded FAQ search
    if q_tokens and cfg.faqs:
        best_faq: dict[str, Any] | None = None
        best_score = 0
        for faq in cfg.faqs:
            fq_text = f"{faq.get('q', '')} {faq.get('a', '')}".lower()
            fq_tokens = set(re.findall(r"[a-z0-9]+", fq_text)) - _STOPWORDS
            overlap = sum(1 for t in q_tokens if t in fq_tokens)
            # Also handle simple singular/stem overlaps (e.g., vegan/vegetarian, park/parking)
            prefix_hits = sum(
                1
                for qt in q_tokens
                if any(ft.startswith(qt[:4]) for ft in fq_tokens if len(qt) >= 4)
            )
            score = max(overlap, prefix_hits)
            if score > best_score:
                best_score = score
                best_faq = faq

        needed = 1 if len(q_tokens) <= 2 else 2
        if best_faq is not None and best_score >= needed and best_faq.get("a"):
            return (
                f"**{best_faq.get('q', 'FAQ')}**\n{best_faq['a']}",
                "FAQKnowledgeAgent",
            )

    # 3. Direct catalog item price / description inquiry
    if any(w in low for w in ("price", "cost", "much", "rate", "charge", "menu", "service")) and (
        cfg.catalog_items
    ):
        for item in cfg.catalog_items:
            iname = str(item.get("name", ""))
            itoks = [t for t in re.findall(r"[a-z0-9]+", iname.lower()) if len(t) >= 3]
            if itoks and any(tok in low for tok in itoks):
                return (
                    f"**{iname}** is **${float(item.get('price', 0)):.2f}** at **{business.name}**"
                    + (f" — {item.get('description')}" if item.get("description") else ".")
                    + f"\nOrder or book anytime at `/site/{business.id}`!",
                    "CatalogConciergeAgent",
                )

    return None, ""


async def suggest_business_faqs(
    business: Business,
    cfg: BusinessAgentConfig,
    overrides: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Generate tailored, accurate FAQs for the business's concierge knowledge base."""
    loc = ", ".join(p for p in (business.address, business.city, business.state) if p) or "our area"
    items_str = ", ".join(str(i.get("name", "")) for i in (cfg.catalog_items or [])[:4])

    llm_raw = await generate_text_with_llm(
        system_prompt=(
            "You create concise FAQ pairs for a local business customer concierge. "
            'Respond ONLY with a JSON array of 5 objects [{"q": "...", "a": "..."}]. '
            "Only state facts consistent with the supplied info."
        ),
        user_prompt=(
            f"Business: {business.name} ({business.category})\n"
            f"Location: {loc}\nPhone: {business.phone or 'see profile'}\n"
            f"Items/Services: {items_str or business.category}\n"
        ),
        overrides=overrides,
        temperature=0.4,
        max_tokens=400,
    )
    if llm_raw:
        try:
            clean = (
                llm_raw.strip()
                .removeprefix("```json")
                .removeprefix("```")
                .removesuffix("```")
                .strip()
            )
            parsed = json.loads(clean)
            if isinstance(parsed, list):
                valid = [
                    {"q": str(x["q"]).strip(), "a": str(x["a"]).strip()}
                    for x in parsed
                    if isinstance(x, dict) and x.get("q") and x.get("a")
                ]
                if valid:
                    return valid[:6]
        except (ValueError, TypeError):
            pass

    cat = (business.category or "").lower()
    faqs = [
        {
            "q": f"Where is {business.name} located and how do I contact you?",
            "a": f"We are at {loc}. Reach us at {business.phone or 'our storefront page'} or book online 24/7.",
        },
        {
            "q": "Can I book an appointment or order pickup online?",
            "a": "Yes! Visit our public storefront page anytime to reserve slots, place pickup orders, or join the waitlist.",
        },
        {
            "q": "Do you offer promo codes or loyalty rewards?",
            "a": "Yes! Returning customers earn loyalty points automatically, and active seasonal promo codes can be applied at checkout.",
        },
    ]
    if any(k in cat for k in ("restaurant", "cafe", "bakery", "food")):
        faqs.extend(
            [
                {
                    "q": "Do you accommodate vegetarian or special dietary requests?",
                    "a": "Yes—we prepare fresh vegetarian options daily and gladly note allergies or customization requests in your order.",
                },
                {
                    "q": "Can we book tables for groups or family celebrations?",
                    "a": "Yes, group bookings are welcome! Add your party details in booking notes so we prepare your table ahead of time.",
                },
            ]
        )
    else:
        faqs.extend(
            [
                {
                    "q": "What is your rescheduling or cancellation policy?",
                    "a": "You can reschedule or cancel any time on WhatsApp (just send 'Cancel booking #ID' or 'Reschedule booking #ID').",
                },
                {
                    "q": f"What are your most popular services at {business.name}?",
                    "a": f"Customers love {items_str or 'our signature local services'}. Full pricing is always visible on our storefront.",
                },
            ]
        )
    return faqs


async def notify_waitlist_for_cancelled_booking(
    db: AsyncSession,
    business: Business,
    booking: Booking,
) -> list[WaitlistEntry]:
    """Alert waiting customers via WhatsApp when a booking is cancelled and a slot reopens."""
    stmt = (
        select(WaitlistEntry)
        .where(
            WaitlistEntry.business_id == business.id,
            WaitlistEntry.preferred_date == booking.booking_date,
            WaitlistEntry.status == WaitlistStatus.WAITING,
        )
        .order_by(WaitlistEntry.created_at.asc())
        .limit(5)
    )
    matches = list((await db.execute(stmt)).scalars().all())
    if not matches:
        return []

    slot_str = booking.booking_time.strftime("%H:%M")
    for entry in matches:
        entry.status = WaitlistStatus.NOTIFIED
        msg = (
            f"Good news {entry.customer_name}! 🎉 A slot just opened at **{business.name}** on "
            f"**{booking.booking_date.isoformat()} at {slot_str}** (your waitlist date). "
            f'Reply *"Book {booking.booking_date.isoformat()} at {slot_str}"* or visit `/site/{business.id}` to claim it!'
        )
        db.add(
            WhatsAppMessage(
                business_id=business.id,
                sender_phone=entry.customer_phone,
                sender_name=entry.customer_name,
                sender_role="assistant",
                direction="outbound",
                message_text=msg,
                agent_used="WaitlistAlertAgent",
            )
        )

    db.add(
        AgentRunLog(
            business_id=business.id,
            trigger_source="waitlist_alert",
            goal=f"Notified {len(matches)} waitlisted guest(s) for reopened slot on {booking.booking_date}",
            agents_invoked=["WaitlistAlertAgent"],
            tools_called=["match_waitlist_slot", "send_whatsapp_alert"],
            steps_summary=[
                {
                    "agent": "WaitlistAlertAgent",
                    "tool": "notify_waitlist",
                    "status": "completed",
                    "detail": f"Alerted {[m.customer_name for m in matches]} for {booking.booking_date} {slot_str}.",
                }
            ],
            outcome="completed",
            duration_ms=2,
        )
    )
    await db.flush()
    return matches


async def launch_segmented_broadcast(
    db: AsyncSession,
    business: Business,
    segment: str,
    topic: str,
    promo_code: str | None = None,
    auto_execute: bool = False,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose and dispatch (or queue in HITL Inbox) a CRM-segmented customer broadcast."""
    started = time.perf_counter()
    customers = await sync_customers_from_activity(db, business.id)
    targets = (
        customers
        if segment == "All"
        else [c for c in customers if c.segment.lower() == segment.lower()]
    )

    promo_clause = ""
    if promo_code:
        val = await validate_and_compute_discount(
            db, business.id, promo_code, subtotal=100.0, increment_use=False
        )
        if not val["valid"]:
            raise ValueError(val["reason"])
        coupon: CouponOffer = val["coupon"]
        desc = (
            f"{int(coupon.discount_value)}% off"
            if coupon.discount_type == DiscountType.PERCENT
            else f"${float(coupon.discount_value):.2f} off"
        )
        promo_clause = f" Use code **{coupon.code}** for {desc}!"

    llm_body = await generate_text_with_llm(
        system_prompt=(
            f"Write a friendly 2-sentence WhatsApp broadcast from {business.name} for "
            f"{segment} customers. Be natural and concise."
        ),
        user_prompt=f"Announcement: {topic}.{promo_clause}",
        overrides=overrides,
        temperature=0.7,
        max_tokens=160,
    )
    base_copy = llm_body or (
        f"Hello from **{business.name}**! ✨ {topic.strip()}.{promo_clause} "
        f"Book or order directly at `/site/{business.id}`!"
    )

    if not targets:
        return {
            "business_id": business.id,
            "segment": segment,
            "targeted_customers": 0,
            "status": "no_recipients",
            "sample_message": base_copy,
            "approval_action_id": None,
        }

    if auto_execute:
        for cust in targets[:50]:
            first_name = cust.name.split()[0] if cust.name else "Friend"
            personal_msg = (
                f"Hi {first_name}, {base_copy[0].lower() + base_copy[1:]}"
                if len(base_copy) > 1
                else base_copy
            )
            db.add(
                WhatsAppMessage(
                    business_id=business.id,
                    sender_phone=cust.phone or cust.email or "crm-on-file",
                    sender_name=cust.name,
                    sender_role="assistant",
                    direction="outbound",
                    message_text=personal_msg,
                    agent_used=f"BroadcastAgent ({segment})",
                )
            )
        db.add(
            AgentRunLog(
                business_id=business.id,
                trigger_source="broadcast",
                goal=f"Sent '{topic}' broadcast to {len(targets)} {segment} customer(s)",
                agents_invoked=["BroadcastCampaignAgent"],
                tools_called=["segment_crm_customers", "dispatch_whatsapp_broadcast"],
                steps_summary=[
                    {
                        "agent": "BroadcastCampaignAgent",
                        "tool": "dispatch_whatsapp_broadcast",
                        "status": "completed",
                        "detail": f"Dispatched to {len(targets)} {segment} customer(s).",
                    }
                ],
                outcome="completed",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        )
        await db.flush()
        return {
            "business_id": business.id,
            "segment": segment,
            "targeted_customers": len(targets),
            "status": "sent",
            "sample_message": base_copy,
            "approval_action_id": None,
        }

    action = AgentApprovalAction(
        business_id=business.id,
        action_type="broadcast_offer",
        title=f"Broadcast to {len(targets)} {segment} Customer(s): {topic[:50]}",
        description=f"Targets {[t.name for t in targets[:5]]}",
        agent_name="BroadcastCampaignAgent",
        reasoning="Bulk customer outreach held in Approval Inbox before mass WhatsApp dispatch.",
        risk_level=RiskLevel.MEDIUM,
        payload={
            "segment": segment,
            "topic": topic,
            "content": base_copy,
            "recipients": [
                {"name": c.name, "contact": c.phone or c.email or "crm-on-file"}
                for c in targets[:50]
            ],
        },
        status=ApprovalStatus.PENDING,
    )
    db.add(action)
    await db.flush()
    return {
        "business_id": business.id,
        "segment": segment,
        "targeted_customers": len(targets),
        "status": "queued_for_approval",
        "sample_message": base_copy,
        "approval_action_id": action.id,
    }


async def compute_revenue_analytics(db: AsyncSession, business: Business) -> dict[str, Any]:
    """Compute real revenue, discount ROI, top menu items, repeat rate, and busiest hours."""
    orders = list(
        (await db.execute(select(OrderRequest).where(OrderRequest.business_id == business.id)))
        .scalars()
        .all()
    )
    bookings = list(
        (await db.execute(select(Booking).where(Booking.business_id == business.id)))
        .scalars()
        .all()
    )
    coupons = list(
        (await db.execute(select(CouponOffer).where(CouponOffer.business_id == business.id)))
        .scalars()
        .all()
    )
    reviews = list(
        (await db.execute(select(Review).where(Review.business_id == business.id))).scalars().all()
    )
    waitlist = list(
        (await db.execute(select(WaitlistEntry).where(WaitlistEntry.business_id == business.id)))
        .scalars()
        .all()
    )
    customers = await sync_customers_from_activity(db, business.id)

    valid_orders = [o for o in orders if o.status != OrderStatus.CANCELLED]
    gross_order_rev = round(
        sum(float(o.subtotal_amount or o.total_amount) for o in valid_orders), 2
    )
    total_discounts = round(sum(float(o.discount_amount or 0.0) for o in valid_orders), 2)
    net_order_rev = round(sum(float(o.total_amount) for o in valid_orders), 2)
    aov = round(net_order_rev / len(valid_orders), 2) if valid_orders else 0.0

    active_bookings = [b for b in bookings if b.status != BookingStatus.CANCELLED]
    est_booking_rev = round(len(active_bookings) * 35.0, 2)
    total_est_rev = round(net_order_rev + est_booking_rev, 2)

    item_qty: Counter[str] = Counter()
    item_rev: Counter[str] = Counter()
    for o in valid_orders:
        for it in o.items or []:
            nm = str(it.get("name", "Item"))
            q = int(it.get("quantity", 1) or 1)
            p = float(it.get("price", 0.0) or 0.0)
            item_qty[nm] += q
            item_rev[nm] += round(p * q, 2)

    top_items = [
        {"name": nm, "units_sold": qty, "gross_revenue": round(item_rev[nm], 2)}
        for nm, qty in item_qty.most_common(5)
    ]

    hour_counts = Counter(f"{b.booking_time.hour:02d}:00" for b in active_bookings)
    busiest_hours = [{"hour": hr, "bookings": cnt} for hr, cnt in hour_counts.most_common(5)]

    repeat_customers = sum(1 for c in customers if c.visit_count >= 2)
    repeat_rate = round((repeat_customers / len(customers)) * 100.0, 1) if customers else 0.0
    total_redemptions = sum(c.uses_count for c in coupons)
    avg_rating = round(sum(r.rating for r in reviews) / len(reviews), 2) if reviews else 0.0

    return {
        "business_id": business.id,
        "business_name": business.name,
        "gross_order_revenue": gross_order_rev,
        "total_discounts_given": total_discounts,
        "net_order_revenue": net_order_rev,
        "estimated_booking_revenue": est_booking_rev,
        "total_estimated_revenue": total_est_rev,
        "average_order_value": aov,
        "total_orders": len(valid_orders),
        "total_active_bookings": len(active_bookings),
        "total_customers": len(customers),
        "repeat_customer_rate_pct": repeat_rate,
        "active_coupons": sum(1 for c in coupons if c.is_active),
        "total_coupon_redemptions": total_redemptions,
        "waitlist_waiting_count": sum(1 for w in waitlist if w.status == WaitlistStatus.WAITING),
        "average_rating": avg_rating,
        "top_ordered_items": top_items,
        "busiest_booking_hours": busiest_hours,
    }


async def localize_content(
    business: Business,
    text: str,
    target_language: str,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Translate or localize customer-facing promos and replies into neighborhood languages."""
    lang = target_language.strip()
    llm_tr = await generate_text_with_llm(
        system_prompt=(
            f"Translate and naturally adapt this local business message into {lang}. "
            "Preserve business names, prices, dates, and promo codes verbatim."
        ),
        user_prompt=text,
        overrides=overrides,
        temperature=0.3,
        max_tokens=300,
    )
    if llm_tr:
        return {
            "business_id": business.id,
            "target_language": lang,
            "original_text": text,
            "translated_text": llm_tr,
            "notes": f"AI-localized into {lang} preserving promo codes & business facts.",
        }

    low_lang = lang.lower()
    salutations = {
        "hindi": f"नमस्ते! {business.name} की ओर से विशेष संदेश:",
        "hinglish": f"Namaste! {business.name} ki taraf se special update:",
        "spanish": f"¡Hola! Novedades de {business.name}:",
        "french": f"Bonjour ! Offre spéciale de {business.name} :",
        "english": f"Hello from {business.name}:",
    }
    prefix = salutations.get(low_lang, f"[{lang}] {business.name}:")
    cta = {
        "hindi": "अभी बुक या ऑर्डर करने के लिए हमारे पेज पर जाएँ!",
        "hinglish": "Abhi book ya order karne ke liye hamare storefront link par click karein!",
        "spanish": "¡Reserva o haz tu pedido hoy mismo en nuestra página!",
        "french": "Réservez ou commandez dès aujourd'hui sur notre boutique en ligne !",
        "english": "Book or order online anytime!",
    }.get(low_lang, "Book or order online today!")

    return {
        "business_id": business.id,
        "target_language": lang,
        "original_text": text,
        "translated_text": f"{prefix} {text.strip()} — {cta}",
        "notes": "Offline localization helper applied regional greeting and call-to-action (connect an LLM key for full neural translation).",
        "raw_metadata": {"mode": "offline_glossary", "utc": datetime.now(UTC).isoformat()},
    }
