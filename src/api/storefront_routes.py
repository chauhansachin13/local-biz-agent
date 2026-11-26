"""Customer-facing public microsite storefront, QR code, printable counter poster, and review form."""

from __future__ import annotations

import html
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.health_and_growth import get_or_create_agent_config
from src.api.deps import get_business_or_404
from src.database import get_db
from src.models.growth_models import CouponOffer, DiscountType
from src.models.review import Review
from src.utils.visuals import generate_qr_svg

router = APIRouter(tags=["Public Storefront"])


@router.get("/site/{business_id}/qr")
async def storefront_qr_svg(
    business_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return a scannable SVG QR code pointing to the business's public storefront."""
    await get_business_or_404(db, business_id)
    base_url = str(request.base_url).rstrip("/")
    svg = generate_qr_svg(f"{base_url}/site/{business_id}")
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Content-Disposition": f'inline; filename="storefront_{business_id}_qr.svg"'},
    )


@router.get("/site/{business_id}/poster", response_class=HTMLResponse)
async def storefront_printable_poster(
    business_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Render a print-ready counter flyer/poster with a scannable QR code."""
    business = await get_business_or_404(db, business_id)
    base_url = str(request.base_url).rstrip("/")
    store_url = f"{base_url}/site/{business_id}"
    svg_qr = generate_qr_svg(store_url)
    name_esc = html.escape(business.name)
    cat_esc = html.escape(business.category.title())
    city_esc = html.escape(business.city or "Local Business")

    poster_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>{name_esc} — Printable Counter QR Poster</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #e2e8f0; margin: 0; padding: 2rem; display: flex; justify-content: center; }}
    .poster {{ background: #ffffff; max-width: 560px; width: 100%; border-radius: 24px; padding: 2.5rem 2rem; text-align: center; box-shadow: 0 12px 32px rgba(15,23,42,0.12); border: 4px solid #1e3a8a; }}
    h1 {{ margin: 0.25rem 0; font-size: 2.1rem; color: #0f172a; }}
    .tag {{ display: inline-block; background: #dbeafe; color: #1e40af; padding: 0.3rem 0.9rem; border-radius: 999px; font-weight: 700; font-size: 0.85rem; }}
    .qr-box {{ margin: 1.5rem auto; width: 240px; height: 240px; padding: 14px; border: 2px dashed #94a3b8; border-radius: 16px; display: flex; align-items: center; justify-content: center; }}
    .qr-box svg {{ width: 100%; height: 100%; }}
    .cta {{ font-size: 1.2rem; font-weight: 700; color: #1e3a8a; margin-bottom: 0.4rem; }}
    .url {{ color: #64748b; font-size: 0.9rem; word-break: break-all; }}
    @media print {{ body {{ background: #fff; padding: 0; }} .no-print {{ display: none; }} }}
    button {{ margin-top: 1.25rem; background: #1e3a8a; color: #fff; border: none; padding: 0.7rem 1.4rem; border-radius: 10px; font-weight: 600; cursor: pointer; font-size: 1rem; }}
  </style>
</head>
<body>
  <div class="poster">
    <span class="tag">{cat_esc} • {city_esc}</span>
    <h1>{name_esc}</h1>
    <p style="color:#475569;">Scan with your phone camera to connect with us instantly!</p>
    <div class="qr-box">{svg_qr}</div>
    <div class="cta">📅 Book • 🛒 Order Pickup • ⭐ Leave a Review</div>
    <div class="url">{html.escape(store_url)}</div>
    <button class="no-print" onclick="window.print()">🖨️ Print Counter Poster</button>
  </div>
</body>
</html>"""
    return HTMLResponse(content=poster_html)


@router.get("/site/{business_id}/menu", response_class=HTMLResponse)
async def storefront_printable_menu(
    business_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Render a print-ready digital menu / price list with active promo codes and QR."""
    business = await get_business_or_404(db, business_id)
    cfg = await get_or_create_agent_config(db, business_id)
    coupons = list(
        (
            await db.execute(
                select(CouponOffer).where(
                    CouponOffer.business_id == business_id,
                    CouponOffer.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    await db.commit()

    base_url = str(request.base_url).rstrip("/")
    store_url = f"{base_url}/site/{business_id}"
    svg_qr = generate_qr_svg(store_url)
    name_esc = html.escape(business.name)
    cat_esc = html.escape(business.category.title())
    city_esc = html.escape(business.city or "Local Community")

    items_html = ""
    for item in cfg.catalog_items or []:
        iname = html.escape(str(item.get("name", "Item")))
        idesc = html.escape(str(item.get("description", "")))
        iprice = float(item.get("price", 0.0) or 0.0)
        items_html += (
            f'<div class="row"><div><strong>{iname}</strong>'
            f'<div class="muted">{idesc}</div></div>'
            f'<div class="price">${iprice:.2f}</div></div>'
        )

    today = date.today()
    live_coupons = [c for c in coupons if c.valid_until is None or c.valid_until >= today]
    promo_html = "".join(
        f'<span class="coupon">🎟️ <strong>{html.escape(c.code)}</strong>: '
        f"{int(c.discount_value)}% off"
        if c.discount_type == DiscountType.PERCENT
        else f'<span class="coupon">🎟️ <strong>{html.escape(c.code)}</strong>: ${c.discount_value:.2f} off'
        + f" — {html.escape(c.title)}</span>"
        for c in live_coupons
    )

    menu_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>{name_esc} — Digital Menu & Services</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f1f5f9; margin: 0; padding: 2rem; color: #0f172a; }}
    .sheet {{ max-width: 720px; margin: 0 auto; background: #fff; border-radius: 18px; padding: 2rem; box-shadow: 0 10px 30px rgba(15,23,42,0.1); }}
    .top {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #e2e8f0; padding-bottom: 1rem; margin-bottom: 1.25rem; gap: 1rem; }}
    .qr {{ width: 110px; height: 110px; flex-shrink: 0; }}
    .qr svg {{ width: 100%; height: 100%; }}
    .row {{ display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 0; border-bottom: 1px solid #f1f5f9; }}
    .price {{ font-weight: 800; color: #1d4ed8; font-size: 1.05rem; margin-left: 1rem; white-space: nowrap; }}
    .muted {{ color: #64748b; font-size: 0.88rem; }}
    .coupon {{ display: inline-block; background: #dcfce7; color: #166534; padding: 0.35rem 0.75rem; border-radius: 999px; font-size: 0.85rem; margin: 0.25rem 0.35rem 0.25rem 0; }}
    @media print {{ body {{ background: #fff; padding: 0; }} .no-print {{ display: none; }} }}
    button {{ background: #1e3a8a; color: #fff; border: none; padding: 0.65rem 1.2rem; border-radius: 10px; font-weight: 600; cursor: pointer; margin-top: 1rem; }}
  </style>
</head>
<body>
  <div class="sheet">
    <div class="top">
      <div>
        <div class="muted">{cat_esc} • {city_esc}</div>
        <h1 style="margin:0.2rem 0;">{name_esc}</h1>
        <div class="muted">Scan QR or visit {html.escape(store_url)} to book & order online</div>
      </div>
      <div class="qr">{svg_qr}</div>
    </div>
    {f'<div style="margin-bottom:1rem;">{promo_html}</div>' if promo_html else ""}
    <h2 style="margin-top:0.5rem;">🛍️ Menu & Price List</h2>
    {items_html or '<p class="muted">Contact us for today’s specials.</p>'}
    <button class="no-print" onclick="window.print()">🖨️ Print Menu Card</button>
  </div>
</body>
</html>"""
    return HTMLResponse(content=menu_html)


@router.get("/site/{business_id}", response_class=HTMLResponse)
async def public_business_storefront(
    business_id: int,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Serve a shareable, mobile-friendly public storefront with bookings, orders, coupons, waitlist, and reviews."""
    business = await get_business_or_404(db, business_id)
    cfg = await get_or_create_agent_config(db, business_id)
    reviews = list(
        (
            await db.execute(
                select(Review)
                .where(Review.business_id == business_id)
                .order_by(Review.rating.desc(), Review.created_at.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    coupons = list(
        (
            await db.execute(
                select(CouponOffer).where(
                    CouponOffer.business_id == business_id,
                    CouponOffer.is_active.is_(True),
                )
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
    today_date = date.today()
    live_coupons = [
        c
        for c in coupons
        if (c.valid_until is None or c.valid_until >= today_date) and c.uses_count < c.max_uses
    ]
    coupon_pills = "".join(
        f'<span class="badge" style="background:#f59e0b;color:#0f172a;margin:0.25rem;">🎟️ Code {html.escape(c.code)} — '
        + (
            f"{int(c.discount_value)}% OFF"
            if c.discount_type == DiscountType.PERCENT
            else f"${c.discount_value:.2f} OFF"
        )
        + (f" (min ${c.min_order_amount:.0f})" if c.min_order_amount > 0 else "")
        + "</span>"
        for c in live_coupons[:3]
    )

    page_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{name_esc} — Book, Order & Review</title>
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
    {f'<div style="margin-top:0.85rem;">{coupon_pills}</div>' if coupon_pills else ""}
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
          <label>Promo Code (optional)</label>
          <div style="display:flex;gap:0.5rem;align-items:center;">
            <input id="ordPromo" placeholder="e.g., LOCAL15" style="margin-top:0.2rem;flex:1;" />
            <button type="button" onclick="checkPromoCode()" style="width:auto;margin-top:0.2rem;padding:0.55rem 0.9rem;background:#0f172a;">Apply</button>
          </div>
          <div id="promoPreview" class="muted" style="margin-top:0.25rem;"></div>
          <label>Notes</label><textarea id="ordNotes" rows="2" placeholder="Any preferences..."></textarea>
          <button type="submit">Submit Order</button>
          <div id="ordMsg" class="msg"></div>
        </form>
      </section>
    </div>

    <div class="grid-2">
      <section class="card" id="waitlist">
        <h2>⏰ Preferred Slot Full? Join the Waitlist</h2>
        <p class="muted">We'll alert you automatically on WhatsApp the moment a cancellation opens up!</p>
        <form id="waitlistForm">
          <div class="grid-2">
            <div><label>Your Name *</label><input id="wlName" required placeholder="Priya" /></div>
            <div><label>WhatsApp Phone *</label><input id="wlPhone" required placeholder="+1-555-0188" /></div>
          </div>
          <div class="grid-2">
            <div><label>Preferred Date *</label><input id="wlDate" type="date" value="{tomorrow}" required /></div>
            <div><label>Preferred Time *</label><input id="wlTime" type="time" value="18:00" required /></div>
          </div>
          <label>Service / Party Size</label><input id="wlService" value="Table / Standard Visit" />
          <button type="submit" style="background:#0f172a;">Join Instant Waitlist</button>
          <div id="wlMsg" class="msg"></div>
        </form>
      </section>

      <section class="card" id="review">
      <h2>⭐ Leave Us a Customer Review</h2>
      <form id="reviewForm">
        <div class="grid-2">
          <div><label>Your Name *</label><input id="revName" required placeholder="Alex Morgan" /></div>
          <div>
            <label>Rating *</label>
            <select id="revRating">
              <option value="5">★★★★★ (5 - Excellent)</option>
              <option value="4">★★★★☆ (4 - Good)</option>
              <option value="3">★★★☆☆ (3 - Okay)</option>
              <option value="2">★★☆☆☆ (2 - Needs Improvement)</option>
              <option value="1">★☆☆☆☆ (1 - Poor)</option>
            </select>
          </div>
        </div>
        <label>Your Feedback *</label>
        <textarea id="revText" rows="3" required placeholder="Tell us about your visit..."></textarea>
        <button type="submit">Submit Review</button>
        <div id="revMsg" class="msg"></div>
      </form>
      </section>
    </div>
  </main>

  <script>
    const BIZ_ID = {business_id};
    async function checkPromoCode() {{
      const code = document.getElementById('ordPromo').value.trim();
      const preview = document.getElementById('promoPreview');
      if (!code) {{ preview.textContent = ''; return; }}
      const sel = document.getElementById('ordItem');
      const opt = sel.options[sel.selectedIndex];
      const qty = parseInt(document.getElementById('ordQty').value || '1', 10);
      const price = parseFloat(opt.getAttribute('data-price') || '0');
      const subtotal = qty * price;
      const resp = await fetch(`/api/growth/${{BIZ_ID}}/coupons/validate`, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ code, subtotal }})
      }});
      const data = await resp.json();
      preview.style.color = data.valid ? '#166534' : '#991b1b';
      preview.textContent = data.valid
        ? `${{data.reason}} New total: $${{data.final_total.toFixed(2)}}`
        : data.reason;
    }}
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
          promo_code: document.getElementById('ordPromo').value.trim() || null,
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
        const discText = data.discount_amount > 0 ? ` (Saved $${{data.discount_amount.toFixed(2)}}!)` : '';
        msg.textContent = `Order #${{data.id}} received! Total: $${{data.total_amount.toFixed(2)}}${{discText}}`;
      }} else {{
        msg.className = 'msg err';
        msg.textContent = data.detail || 'Could not place order.';
      }}
    }});

    document.getElementById('waitlistForm').addEventListener('submit', async (e) => {{
      e.preventDefault();
      const msg = document.getElementById('wlMsg');
      msg.className = 'msg';
      const resp = await fetch(`/api/growth/${{BIZ_ID}}/waitlist`, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          customer_name: document.getElementById('wlName').value,
          customer_phone: document.getElementById('wlPhone').value,
          preferred_date: document.getElementById('wlDate').value,
          preferred_time: document.getElementById('wlTime').value.slice(0, 5),
          service: document.getElementById('wlService').value || 'Reservation'
        }})
      }});
      const data = await resp.json();
      if (resp.ok) {{
        msg.className = 'msg ok';
        msg.textContent = `Added to waitlist (#${{data.id}}) for ${{data.preferred_date}} at ${{data.preferred_time}}!`;
      }} else {{
        msg.className = 'msg err';
        msg.textContent = data.detail || 'Could not join waitlist.';
      }}
    }});

    document.getElementById('reviewForm').addEventListener('submit', async (e) => {{
      e.preventDefault();
      const msg = document.getElementById('revMsg');
      msg.className = 'msg';
      const resp = await fetch(`/api/reviews/${{BIZ_ID}}/submit`, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          reviewer_name: document.getElementById('revName').value,
          rating: parseInt(document.getElementById('revRating').value, 10),
          review_text: document.getElementById('revText').value,
          platform: 'storefront'
        }})
      }});
      const data = await resp.json();
      if (resp.ok) {{
        msg.className = 'msg ok';
        msg.textContent = `Thank you for your ${{data.rating}}★ review! Our AI manager has logged it.`;
      }} else {{
        msg.className = 'msg err';
        msg.textContent = data.detail || 'Could not submit review.';
      }}
    }});
  </script>
</body>
</html>"""
    return HTMLResponse(content=page_html)
