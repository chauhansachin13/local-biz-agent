"""Customer-facing public microsite storefront supporting direct bookings and online orders."""

from __future__ import annotations

import html
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.health_and_growth import get_or_create_agent_config
from src.api.deps import get_business_or_404
from src.database import get_db
from src.models.review import Review

router = APIRouter(tags=["Public Storefront"])


@router.get("/site/{business_id}", response_class=HTMLResponse)
async def public_business_storefront(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Serve a shareable, mobile-friendly public storefront with online booking and ordering."""
    business = await get_business_or_404(db, business_id)
    cfg = await get_or_create_agent_config(db, business_id)
    reviews = list(
        (
            await db.execute(
                select(Review)
                .where(Review.business_id == business_id)
                .order_by(Review.rating.desc(), Review.created_at.desc())
                .limit(4)
            )
        )
        .scalars()
        .all()
    )
    await db.commit()

    name_esc = html.escape(business.name)
    cat_esc = html.escape(business.category.title())
    desc_esc = html.escape(business.description or "Welcome to our local business!")
    loc_parts = [p for p in (business.address, business.city, business.state) if p]
    loc_esc = html.escape(", ".join(loc_parts) or "Local Community")
    phone_esc = html.escape(business.phone or "Call for details")

    avg_rating = round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else 5.0
    gbp_badge = (
        '<span class="badge verified">✓ Verified Google Business</span>'
        if business.google_business_id
        else '<span class="badge">Local Business Page</span>'
    )

    hours_rows = ""
    if business.operating_hours:
        for day_name, hcfg in business.operating_hours.items():
            if isinstance(hcfg, dict):
                hrs = (
                    "Closed"
                    if hcfg.get("closed")
                    else f"{hcfg.get('open', '09:00')} – {hcfg.get('close', '18:00')}"
                )
                hours_rows += (
                    f"<li><strong>{html.escape(day_name.title())}:</strong> {html.escape(hrs)}</li>"
                )

    catalog_cards = ""
    options_html = ""
    for item in cfg.catalog_items:
        iname = html.escape(str(item.get("name", "Service")))
        idesc = html.escape(str(item.get("description", "")))
        iprice = float(item.get("price", 0.0) or 0.0)
        price_label = f"${iprice:.2f}" if iprice > 0 else "Book Online"
        catalog_cards += (
            f'<div class="item-card"><div><strong>{iname}</strong>'
            f'<div class="muted">{idesc}</div></div>'
            f'<div class="price">{price_label}</div></div>'
        )
        options_html += (
            f'<option value="{iname}" data-price="{iprice}">{iname} ({price_label})</option>'
        )

    if not options_html:
        options_html = (
            '<option value="Standard Service" data-price="25">Standard Service ($25.00)</option>'
        )

    review_cards = ""
    for r in reviews:
        stars = "★" * r.rating + "☆" * (5 - r.rating)
        review_cards += (
            f'<div class="review-card"><div class="stars">{stars} • {html.escape(r.reviewer_name)}</div>'
            f"<p>{html.escape(r.review_text or '')}</p></div>"
        )

    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    page_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{name_esc} — Book & Order Online</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; background: #f8fafc; color: #0f172a; line-height: 1.5; }}
    .hero {{ background: linear-gradient(135deg, #0f172a, #1e3a8a); color: #fff; padding: 2.5rem 1.5rem; text-align: center; }}
    .hero h1 {{ margin: 0.4rem 0; font-size: 2rem; }}
    .badge {{ display: inline-block; padding: 0.25rem 0.75rem; border-radius: 999px; background: rgba(255,255,255,0.18); font-size: 0.8rem; font-weight: 600; }}
    .badge.verified {{ background: #16a34a; }}
    .container {{ max-width: 1020px; margin: 1.5rem auto; padding: 0 1rem 3rem; display: grid; grid-template-columns: 1fr; gap: 1.25rem; }}
    @media (min-width: 780px) {{ .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; }} }}
    .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; padding: 1.25rem; box-shadow: 0 2px 8px rgba(15,23,42,0.04); }}
    .card h2 {{ margin-top: 0; font-size: 1.15rem; border-bottom: 1px solid #f1f5f9; padding-bottom: 0.5rem; }}
    .item-card {{ display: flex; justify-content: space-between; align-items: center; padding: 0.65rem 0; border-bottom: 1px solid #f1f5f9; }}
    .price {{ font-weight: 700; color: #1d4ed8; white-space: nowrap; margin-left: 1rem; }}
    .muted {{ color: #64748b; font-size: 0.88rem; }}
    label {{ display: block; font-size: 0.85rem; font-weight: 600; margin-top: 0.65rem; color: #334155; }}
    input, select, textarea {{ width: 100%; padding: 0.55rem 0.7rem; border: 1px solid #cbd5e1; border-radius: 8px; margin-top: 0.2rem; font-size: 0.95rem; }}
    button {{ margin-top: 0.9rem; width: 100%; background: #2563eb; color: #fff; border: none; border-radius: 8px; padding: 0.7rem; font-size: 1rem; font-weight: 600; cursor: pointer; }}
    button:hover {{ background: #1d4ed8; }}
    .msg {{ margin-top: 0.7rem; padding: 0.6rem; border-radius: 8px; font-size: 0.9rem; display: none; }}
    .msg.ok {{ display: block; background: #dcfce7; color: #166534; }}
    .msg.err {{ display: block; background: #fee2e2; color: #991b1b; }}
    .stars {{ color: #d97706; font-weight: 600; font-size: 0.9rem; }}
    .review-card {{ padding: 0.6rem 0; border-bottom: 1px solid #f1f5f9; }}
    ul.hours {{ list-style: none; padding: 0; margin: 0; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <header class="hero">
    {gbp_badge}
    <h1>{name_esc}</h1>
    <p>{cat_esc} • 📍 {loc_esc} • 📞 {phone_esc} • ★ {avg_rating}/5</p>
    <p style="max-width:680px;margin:0.5rem auto 0;opacity:0.9;">{desc_esc}</p>
  </header>

  <main class="container">
    <div class="grid-2">
      <section class="card">
        <h2>🛍️ Menu & Services</h2>
        {catalog_cards or '<p class="muted">Contact us for custom services.</p>'}
      </section>
      <section class="card">
        <h2>🕒 Hours & Customer Reviews</h2>
        <ul class="hours">{hours_rows or "<li>Open Daily</li>"}</ul>
        <h3 style="margin-top:1rem;font-size:1rem;">Recent Reviews</h3>
        {review_cards or '<p class="muted">No reviews yet.</p>'}
      </section>
    </div>

    <div class="grid-2">
      <section class="card">
        <h2>📅 Book an Appointment / Table</h2>
        <form id="bookingForm">
          <label>Your Name *</label><input id="bkName" required />
          <label>Phone *</label><input id="bkPhone" required placeholder="(555) 123-4567" />
          <label>Email *</label><input id="bkEmail" type="email" required placeholder="you@example.com" />
          <label>Service *</label><input id="bkService" required value="Standard Visit" />
          <label>Date *</label><input id="bkDate" type="date" value="{tomorrow}" required />
          <label>Time *</label><input id="bkTime" type="time" value="12:00" required />
          <button type="submit">Confirm Booking</button>
          <div id="bkMsg" class="msg"></div>
        </form>
      </section>

      <section class="card">
        <h2>🛒 Place an Online Order</h2>
        <form id="orderForm">
          <label>Your Name *</label><input id="ordName" required />
          <label>Phone *</label><input id="ordPhone" required placeholder="(555) 123-4567" />
          <label>Select Item *</label><select id="ordItem">{options_html}</select>
          <label>Quantity *</label><input id="ordQty" type="number" min="1" max="20" value="1" required />
          <label>Fulfillment</label>
          <select id="ordType"><option value="pickup">Store Pickup</option><option value="delivery">Local Delivery</option><option value="dine_in">Dine-In</option></select>
          <label>Notes</label><textarea id="ordNotes" rows="2" placeholder="Any preferences..."></textarea>
          <button type="submit">Submit Order</button>
          <div id="ordMsg" class="msg"></div>
        </form>
      </section>
    </div>
  </main>

  <script>
    const BIZ_ID = {business_id};
    document.getElementById('bookingForm').addEventListener('submit', async (e) => {{
      e.preventDefault();
      const msg = document.getElementById('bkMsg');
      msg.className = 'msg';
      const resp = await fetch(`/api/bookings/${{BIZ_ID}}/book`, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          customer_name: document.getElementById('bkName').value,
          customer_phone: document.getElementById('bkPhone').value,
          customer_email: document.getElementById('bkEmail').value,
          service: document.getElementById('bkService').value,
          booking_date: document.getElementById('bkDate').value,
          booking_time: document.getElementById('bkTime').value + ':00',
          duration_minutes: 60
        }})
      }});
      const data = await resp.json();
      if (resp.ok) {{
        msg.className = 'msg ok';
        msg.textContent = `Booking #${{data.id}} confirmed for ${{data.booking_date}} at ${{data.booking_time}}!`;
      }} else {{
        msg.className = 'msg err';
        msg.textContent = data.detail || 'Could not complete booking.';
      }}
    }});

    document.getElementById('orderForm').addEventListener('submit', async (e) => {{
      e.preventDefault();
      const msg = document.getElementById('ordMsg');
      msg.className = 'msg';
      const sel = document.getElementById('ordItem');
      const opt = sel.options[sel.selectedIndex];
      const resp = await fetch(`/api/orders/${{BIZ_ID}}/order`, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          customer_name: document.getElementById('ordName').value,
          customer_phone: document.getElementById('ordPhone').value,
          fulfillment_type: document.getElementById('ordType').value,
          notes: document.getElementById('ordNotes').value || null,
          items: [{{
            name: opt.value,
            quantity: parseInt(document.getElementById('ordQty').value, 10),
            price: parseFloat(opt.getAttribute('data-price') || '0')
          }}]
        }})
      }});
      const data = await resp.json();
      if (resp.ok) {{
        msg.className = 'msg ok';
        msg.textContent = `Order #${{data.id}} received! Total: $${{data.total_amount.toFixed(2)}}`;
      }} else {{
        msg.className = 'msg err';
        msg.textContent = data.detail || 'Could not place order.';
      }}
    }});
  </script>
</body>
</html>"""
    return HTMLResponse(content=page_html)
