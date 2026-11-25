"""Pillow promo graphic generator and scannable QR SVG/PNG utilities."""

from __future__ import annotations

import io
import textwrap

import qrcode
import qrcode.image.svg
from PIL import Image, ImageDraw, ImageFont


def generate_qr_svg(url: str) -> str:
    """Generate a crisp, scannable SVG QR code string for a business URL."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")


def _load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSDisplay.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def generate_promo_poster_png(
    business_name: str,
    category: str,
    city: str,
    headline: str,
    offer_text: str,
    promo_code: str,
    storefront_url: str,
    avg_rating: float = 4.8,
) -> bytes:
    """Render a branded 1080x1080 PNG social/WhatsApp promo card with embedded QR code."""
    size = 1080
    img = Image.new("RGB", (size, size), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)

    # Gradient-like modern card background bands
    for y in range(size):
        ratio = y / size
        r = int(15 + (30 - 15) * ratio)
        g = int(23 + (58 - 23) * ratio)
        b = int(42 + (138 - 42) * ratio)
        draw.line([(0, y), (size, y)], fill=(r, g, b))

    # Inner white/glass accent card
    draw.rounded_rectangle([(56, 56), (size - 56, size - 56)], radius=36, fill=(255, 255, 255))
    draw.rounded_rectangle([(56, 56), (size - 56, 250)], radius=36, fill=(30, 58, 138))
    draw.rectangle([(56, 210), (size - 56, 250)], fill=(30, 58, 138))

    font_title = _load_font(54, bold=True)
    font_sub = _load_font(28, bold=False)
    font_head = _load_font(52, bold=True)
    font_body = _load_font(34, bold=False)
    font_pill = _load_font(32, bold=True)
    font_small = _load_font(24, bold=False)

    loc_part = f" • {city}" if city else ""
    draw.text((96, 94), business_name[:32], fill=(255, 255, 255), font=font_title)
    draw.text(
        (96, 168),
        f"{category.title()}{loc_part}  |  {avg_rating:.1f} ★ Local Favorite",
        fill=(219, 234, 254),
        font=font_sub,
    )

    # Headline wrapped cleanly
    y_cursor = 300
    for line in textwrap.wrap(headline or "Special Neighborhood Offer", width=26)[:3]:
        draw.text((96, y_cursor), line, fill=(15, 23, 42), font=font_head)
        y_cursor += 68

    y_cursor += 20
    for line in textwrap.wrap(offer_text or "Book online or order pickup today.", width=38)[:4]:
        draw.text((96, y_cursor), line, fill=(71, 85, 105), font=font_body)
        y_cursor += 46

    # Promo code pill
    if promo_code:
        pill_top = max(y_cursor + 24, 640)
        draw.rounded_rectangle(
            [(96, pill_top), (540, pill_top + 76)],
            radius=20,
            fill=(254, 243, 199),
            outline=(245, 158, 11),
            width=3,
        )
        draw.text(
            (126, pill_top + 20), f"USE CODE: {promo_code[:14]}", fill=(146, 64, 14), font=font_pill
        )

    # Scannable QR code in bottom-right corner
    qr = qrcode.QRCode(
        version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=2
    )
    qr.add_data(storefront_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_img = qr_img.resize((220, 220))
    img.paste(qr_img, (size - 310, size - 320))

    draw.text(
        (96, size - 190), "Scan QR to Book, Order & Review", fill=(30, 58, 138), font=font_pill
    )
    draw.text((96, size - 140), storefront_url[:52], fill=(100, 116, 139), font=font_small)

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()
