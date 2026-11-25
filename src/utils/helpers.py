import re
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_EMAIL_REGEX = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$"
)
_IST_ZONE = ZoneInfo("Asia/Kolkata")


def generate_slug(name: str) -> str:
    """Generate a URL-friendly lowercase slug from a business or entity name."""
    if not name or not name.strip():
        return ""
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    lowercased = normalized.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowercased).strip("-")
    return slug


def format_phone(phone: str, default_country_code: str = "+91") -> str:
    """Normalize and format a phone number into a clean, consistent representation.

    Examples:
        '9876543210' -> '+91 98765 43210'
        '+1 (415) 555-2671' -> '+1 4155552671'
    """
    if not phone or not phone.strip():
        raise ValueError("Phone number cannot be empty.")

    stripped = phone.strip()
    has_plus = stripped.startswith("+")
    digits = re.sub(r"\D", "", stripped)

    if len(digits) < 7 or len(digits) > 15:
        raise ValueError(f"Invalid phone number length: '{phone}'")

    if not has_plus and len(digits) == 10:
        prefix = default_country_code if default_country_code.startswith("+") else f"+{default_country_code}"
        if prefix == "+91":
            return f"+91 {digits[:5]} {digits[5:]}"
        return f"{prefix} {digits[:3]}-{digits[3:6]}-{digits[6:]}"

    if has_plus and digits.startswith("91") and len(digits) == 12:
        local = digits[2:]
        return f"+91 {local[:5]} {local[5:]}"

    if has_plus and digits.startswith("1") and len(digits) == 11:
        local = digits[1:]
        return f"+1 ({local[:3]}) {local[3:6]}-{local[6:]}"

    return f"+{digits}" if has_plus else digits


def validate_email(email: str) -> bool:
    """Return True if the provided string is a syntactically valid email address."""
    if not email or not isinstance(email, str):
        return False
    candidate = email.strip()
    if len(candidate) > 254 or ".." in candidate:
        return False
    if not _EMAIL_REGEX.match(candidate):
        return False
    local, domain = candidate.rsplit("@", 1)
    if len(local) > 64 or len(domain) > 253:
        return False
    tld = domain.rsplit(".", 1)[-1]
    return len(tld) >= 2 and not tld.isdigit()


def truncate_text(text: str, max_len: int = 100, suffix: str = "...") -> str:
    """Truncate text to at most `max_len` characters, appending `suffix` if shortened."""
    if max_len < 0:
        raise ValueError("max_len must be non-negative.")
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    if max_len <= len(suffix):
        return suffix[:max_len]
    cut = text[: max_len - len(suffix)].rstrip()
    return f"{cut}{suffix}"


def get_current_ist_time() -> datetime:
    """Return the current timezone-aware datetime in Indian Standard Time (IST)."""
    try:
        return datetime.now(_IST_ZONE)
    except Exception:
        return datetime.now(timezone(timedelta(hours=5, minutes=30)))
