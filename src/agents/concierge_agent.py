"""WhatsApp Business Concierge Agent for customer inquiries, bookings, orders, and owner commands."""

from __future__ import annotations

import re
from datetime import date, time, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.booking_agent import BookingAgent
from src.agents.health_and_growth import get_or_create_agent_config
from src.agents.llm_client import generate_text_with_llm
from src.agents.orchestrator import BizPresenceOrchestrator
from src.models.agent_models import FulfillmentType, OrderRequest, OrderStatus, WhatsAppMessage
from src.models.booking import Booking, BookingStatus
from src.models.business import Business


async def handle_whatsapp_message(
    db: AsyncSession,
    business: Business,
    sender_phone: str,
    sender_name: str,
    sender_role: str,
    message_text: str,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Process an inbound WhatsApp message from a customer or business owner and persist the exchange."""
    cfg = await get_or_create_agent_config(db, business.id)

    db.add(
        WhatsAppMessage(
            business_id=business.id,
            sender_phone=sender_phone,
            sender_name=sender_name,
            sender_role=sender_role,
            direction="inbound",
            message_text=message_text,
            agent_used="IncomingWebhook",
        )
    )

    if sender_role == "owner":
        orch = BizPresenceOrchestrator()
        res = await orch.handle_chat(
            db=db,
            business=business,
            message=message_text,
            auto_execute=True,
            session_id=f"wa_{sender_phone}",
            language=cfg.preferred_language,
            context=overrides,
        )
        reply = res["reply"]
        agent_used = f"OwnerSupervisor ({res['intent']})"
        extra = {"plan": res.get("plan", []), "actions_taken": res.get("actions_taken", [])}
    else:
        reply, agent_used, extra = await _handle_customer_message(
            db=db,
            business=business,
            cfg=cfg,
            sender_phone=sender_phone,
            sender_name=sender_name,
            message_text=message_text,
            overrides=overrides,
        )

    db.add(
        WhatsAppMessage(
            business_id=business.id,
            sender_phone=sender_phone,
            sender_name=business.name,
            sender_role="assistant",
            direction="outbound",
            message_text=reply,
            agent_used=agent_used,
        )
    )
    await db.flush()

    return {
        "business_id": business.id,
        "sender_role": sender_role,
        "agent_used": agent_used,
        "reply": reply,
        "extra": extra,
    }


async def _handle_customer_message(
    db: AsyncSession,
    business: Business,
    cfg: Any,
    sender_phone: str,
    sender_name: str,
    message_text: str,
    overrides: dict[str, Any] | None,
) -> tuple[str, str, dict[str, Any]]:
    low = message_text.lower()
    booking_agent = BookingAgent()

    # 1. Customer ordering via WhatsApp
    if any(w in low for w in ("order", "pickup", "delivery", "buy")):
        matched_item = None
        for item in cfg.catalog_items or []:
            iname = str(item.get("name", ""))
            if iname and any(tok in low for tok in iname.lower().split() if len(tok) > 3):
                matched_item = item
                break
        if matched_item is None and cfg.catalog_items:
            matched_item = cfg.catalog_items[0]

        if matched_item and any(w in low for w in ("confirm", "place", "want", "please", "order")):
            qty_match = re.search(r"\b(\d+)\b", low)
            qty = max(1, min(10, int(qty_match.group(1)))) if qty_match else 1
            price = float(matched_item.get("price", 0.0) or 0.0)
            fulfill = FulfillmentType.DELIVERY if "delivery" in low else FulfillmentType.PICKUP
            order = OrderRequest(
                business_id=business.id,
                customer_name=sender_name,
                customer_phone=sender_phone,
                items=[{"name": matched_item["name"], "quantity": qty, "price": price}],
                total_amount=round(price * qty, 2),
                fulfillment_type=fulfill,
                status=OrderStatus.NEW,
                notes=f"Placed via WhatsApp: {message_text[:140]}",
            )
            db.add(order)
            await db.flush()
            return (
                f"Got it, {sender_name}! ✅ Your WhatsApp order **#{order.id}** for "
                f"**{qty}× {matched_item['name']}** (${order.total_amount:.2f}, {fulfill.value}) "
                f"has been sent to **{business.name}**. We'll message you once it's ready!",
                "WhatsAppOrderAgent",
                {"order_id": order.id, "total_amount": order.total_amount},
            )

        menu_lines = "\n".join(
            f"- {it['name']} (${float(it.get('price', 0)):.2f})"
            for it in (cfg.catalog_items or [])[:5]
        )
        return (
            f"Here's what you can order right now from **{business.name}**:\n{menu_lines}\n\n"
            'Reply e.g. *"Order 2 Signature Combo for pickup"* and I\'ll place it right away!',
            "WhatsAppOrderAgent",
            {},
        )

    # 2. Customer booking / table / appointment inquiry via WhatsApp
    if any(
        w in low
        for w in (
            "book",
            "table",
            "slot",
            "appointment",
            "reserve",
            "available",
            "tomorrow",
            "today",
        )
    ):
        target_date = date.today() + timedelta(days=1) if "tomorrow" in low else date.today()
        time_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", low)
        if time_match and any(w in low for w in ("book", "reserve")):
            hr = int(time_match.group(1))
            mn = int(time_match.group(2) or 0)
            mer = time_match.group(3)
            if mer == "pm" and hr < 12:
                hr += 12
            elif mer == "am" and hr == 12:
                hr = 0
            hr = max(0, min(23, hr))
            start_min = hr * 60 + mn
            conflict = await booking_agent.has_conflict(db, business, target_date, start_min, 60)
            if not conflict:
                bk = Booking(
                    business_id=business.id,
                    customer_name=sender_name,
                    customer_email=f"{re.sub(r'[^a-z0-9]', '', sender_name.lower()) or 'guest'}@whatsapp.local",
                    customer_phone=sender_phone,
                    service=f"WhatsApp {business.category.title()} Booking",
                    booking_date=target_date,
                    booking_time=time(hr, mn),
                    duration_minutes=60,
                    status=BookingStatus.CONFIRMED,
                    notes=f"Booked via WhatsApp: {message_text[:140]}",
                )
                db.add(bk)
                await db.flush()
                return (
                    f"Confirmed, {sender_name}! 📅 Your booking **#{bk.id}** at **{business.name}** "
                    f"is set for **{target_date.isoformat()} at {hr:02d}:{mn:02d}**. See you soon!",
                    "WhatsAppBookingAgent",
                    {"booking_id": bk.id},
                )

        avail = await booking_agent.get_availability(db, business, target_date)
        open_slots = [s["start_time"] for s in avail["slots"] if s["available"]]
        return (
            f"Hi {sender_name}! On **{target_date.isoformat()}**, **{business.name}** has open slots at: "
            f"{', '.join(open_slots[:6]) if open_slots else 'Fully booked / Closed'}.\n\n"
            'Reply *"Book tomorrow at 18:00"* to confirm instantly!',
            "WhatsAppBookingAgent",
            {"open_slots": open_slots[:6]},
        )

    # 3. Hours / location / general FAQ
    if any(w in low for w in ("hour", "open", "close", "address", "where", "location", "phone")):
        loc = (
            ", ".join(p for p in (business.address, business.city, business.state) if p)
            or "Ask for directions"
        )
        return (
            f"**{business.name}** is located at 📍 {loc} (📞 {business.phone or 'see profile'}).\n"
            f"You can also book or order online anytime at `/site/{business.id}`!",
            "WhatsAppConciergeAgent",
            {},
        )

    # 4. General conversational concierge
    llm_reply = await generate_text_with_llm(
        system_prompt=(
            f"You are the friendly WhatsApp customer concierge for {business.name} ({business.category}). "
            f"Address: {business.address or ''}, {business.city or ''}. Reply concisely in 2 sentences."
        ),
        user_prompt=f"Customer {sender_name} says: {message_text}",
        overrides=overrides,
        temperature=0.6,
        max_tokens=160,
    )
    return (
        llm_reply
        or (
            f"Hi {sender_name}! Welcome to **{business.name}**. Ask me about our hours, "
            'open booking slots, or menu items—or reply *"Book tomorrow at 18:00"* or *"Order pickup"*!'
        ),
        "WhatsAppConciergeAgent",
        {},
    )
