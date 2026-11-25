"""LangChain tools for customer booking management backed by SQLite.

Provides `@tool` functions and a `BookingTools` wrapper that persist and query
appointments in the SQLite database configured via `config.settings`.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from langchain_core.tools import tool

from config.settings import settings

logger = logging.getLogger(__name__)

DEFAULT_TIME_SLOTS = [
    "09:00",
    "10:00",
    "11:00",
    "12:00",
    "13:00",
    "14:00",
    "15:00",
    "16:00",
    "17:00",
]


def _resolve_sqlite_path() -> Path:
    """Resolve SQLite database path from `config.settings`."""
    explicit = getattr(settings, "SQLITE_DB_PATH", None)
    if explicit:
        return Path(explicit)
    db_url = getattr(settings, "database_url", "sqlite:///./bizpresence.db")
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if db_url.startswith(prefix):
            raw = db_url.removeprefix(prefix)
            return Path(raw) if raw and raw != ":memory:" else Path("./bizpresence.db")
    return Path("./bizpresence.db")


@contextmanager
def _get_db_connection() -> Iterator[sqlite3.Connection]:
    """Yield an initialized SQLite connection with row dictionary access."""
    db_path = _resolve_sqlite_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                booking_id TEXT PRIMARY KEY,
                business_id INTEGER NOT NULL,
                customer_name TEXT NOT NULL,
                customer_email TEXT,
                customer_phone TEXT,
                service_name TEXT NOT NULL,
                booking_date TEXT NOT NULL,
                booking_time TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL DEFAULT 60,
                status TEXT NOT NULL DEFAULT 'confirmed',
                notes TEXT,
                cancellation_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        yield conn
    finally:
        conn.close()


def _get_booking_schema(conn: sqlite3.Connection) -> set[str]:
    """Return column names present in the `bookings` table."""
    rows = conn.execute("PRAGMA table_info(bookings)").fetchall()
    return {row["name"] for row in rows}


def _normalize_business_id(business_id: Any) -> int:
    try:
        return int(business_id)
    except (TypeError, ValueError):
        return 1


@tool
def check_availability(business_id: str, date: str) -> list:
    """Check open appointment time slots for a business on a given date.

    Args:
        business_id: Business ID (numeric string or integer).
        date: Target date in `YYYY-MM-DD` format.

    Returns:
        List of available time slot dictionaries (`time`, `available`, `duration_minutes`).
    """
    biz_id = _normalize_business_id(business_id)
    with _get_db_connection() as conn:
        cols = _get_booking_schema(conn)
        time_col = "start_time" if "start_time" in cols else "booking_time"
        rows = conn.execute(
            f"""
            SELECT {time_col} AS slot_time FROM bookings
            WHERE business_id = ? AND booking_date = ? AND status = 'confirmed'
            """,
            (biz_id, date),
        ).fetchall()

    booked_times = {str(row["slot_time"])[:5] for row in rows}
    available_slots = [
        {
            "business_id": biz_id,
            "date": date,
            "time": slot,
            "available": True,
            "duration_minutes": 60,
        }
        for slot in DEFAULT_TIME_SLOTS
        if slot not in booked_times
    ]

    logger.info(
        "[Booking DB] Checked availability business_id=%s date=%s open_slots=%d",
        biz_id,
        date,
        len(available_slots),
    )
    return available_slots


@tool
def create_booking(booking_data: dict) -> str:
    """Create and persist a new customer booking in the SQLite database.

    Args:
        booking_data: Dictionary containing `business_id`, `customer_name`,
            `service_name` (or `service`), `booking_date` (or `date`, YYYY-MM-DD),
            `booking_time` (or `time`, HH:MM), and optional `customer_email`,
            `customer_phone`, `duration_minutes`, `notes`.

    Returns:
        JSON string confirming the created booking ID and details, or an error
        if the slot is already taken or required fields are missing.
    """
    biz_id = _normalize_business_id(booking_data.get("business_id", 1))
    customer_name = str(booking_data.get("customer_name", "")).strip()
    service_name = str(
        booking_data.get("service_name") or booking_data.get("service") or ""
    ).strip()
    booking_date = str(
        booking_data.get("booking_date") or booking_data.get("date") or ""
    ).strip()
    booking_time = str(
        booking_data.get("booking_time") or booking_data.get("time") or ""
    ).strip()

    missing = [
        field
        for field, val in [
            ("customer_name", customer_name),
            ("service_name", service_name),
            ("booking_date", booking_date),
            ("booking_time", booking_time),
        ]
        if not val
    ]
    if missing:
        return json.dumps(
            {
                "status": "error",
                "message": f"Missing required booking fields: {', '.join(missing)}.",
            }
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    booking_id = f"bkg_{uuid.uuid4().hex[:10]}"

    with _get_db_connection() as conn:
        cols = _get_booking_schema(conn)
        is_orm_schema = "start_time" in cols and "booking_id" not in cols
        time_col = "start_time" if is_orm_schema else "booking_time"
        id_col = "id" if is_orm_schema else "booking_id"

        conflict = conn.execute(
            f"""
            SELECT {id_col} AS existing_id FROM bookings
            WHERE business_id = ? AND booking_date = ? AND {time_col} = ? AND status = 'confirmed'
            """,
            (biz_id, booking_date, booking_time),
        ).fetchone()
        if conflict:
            return json.dumps(
                {
                    "status": "conflict",
                    "message": (
                        f"Time slot {booking_time} on {booking_date} is already booked "
                        f"(booking_id={conflict['existing_id']})."
                    ),
                }
            )

        if is_orm_schema:
            cursor = conn.execute(
                """
                INSERT INTO bookings (
                    business_id, customer_name, customer_email, customer_phone,
                    service_name, party_size, booking_date, start_time,
                    duration_minutes, status, source, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', 'agent', ?, ?, ?)
                """,
                (
                    biz_id,
                    customer_name,
                    booking_data.get("customer_email") or "",
                    booking_data.get("customer_phone") or "",
                    service_name,
                    int(booking_data.get("party_size", 1)),
                    booking_date,
                    booking_time,
                    int(booking_data.get("duration_minutes", 60)),
                    booking_data.get("notes") or "",
                    now_iso,
                    now_iso,
                ),
            )
            booking_id = str(cursor.lastrowid)
        else:
            conn.execute(
                """
                INSERT INTO bookings (
                    booking_id, business_id, customer_name, customer_email,
                    customer_phone, service_name, booking_date, booking_time,
                    duration_minutes, status, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', ?, ?, ?)
                """,
                (
                    booking_id,
                    biz_id,
                    customer_name,
                    booking_data.get("customer_email"),
                    booking_data.get("customer_phone"),
                    service_name,
                    booking_date,
                    booking_time,
                    int(booking_data.get("duration_minutes", 60)),
                    booking_data.get("notes"),
                    now_iso,
                    now_iso,
                ),
            )
        conn.commit()

    logger.info(
        "[Booking DB] Created booking_id=%s business_id=%s date=%s time=%s",
        booking_id,
        biz_id,
        booking_date,
        booking_time,
    )
    return json.dumps(
        {
            "status": "confirmed",
            "booking_id": booking_id,
            "business_id": biz_id,
            "customer_name": customer_name,
            "service_name": service_name,
            "booking_date": booking_date,
            "booking_time": booking_time,
            "created_at": now_iso,
            "message": f"Booking {booking_id} confirmed for {customer_name} on {booking_date} at {booking_time}.",
        },
        indent=2,
    )


@tool
def cancel_booking(booking_id: str, reason: Optional[str] = None) -> str:
    """Cancel an existing booking by its booking ID in the SQLite database.

    Args:
        booking_id: Unique booking identifier (e.g. `bkg_1234abcd`).
        reason: Optional reason for cancellation.

    Returns:
        JSON string confirming cancellation or reporting if the booking was not found.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    with _get_db_connection() as conn:
        cols = _get_booking_schema(conn)
        is_orm_schema = "start_time" in cols and "booking_id" not in cols
        id_col = "id" if is_orm_schema else "booking_id"
        lookup_id: Any = int(booking_id) if (is_orm_schema and str(booking_id).isdigit()) else booking_id

        row = conn.execute(
            f"SELECT * FROM bookings WHERE {id_col} = ?", (lookup_id,)
        ).fetchone()
        if not row:
            return json.dumps(
                {"status": "not_found", "message": f"Booking '{booking_id}' was not found."}
            )
        if row["status"] == "cancelled":
            return json.dumps(
                {
                    "status": "already_cancelled",
                    "booking_id": booking_id,
                    "message": f"Booking '{booking_id}' is already cancelled.",
                }
            )

        if is_orm_schema:
            notes = row["notes"] or ""
            updated_notes = f"{notes}\nCancelled: {reason}".strip() if reason else notes
            conn.execute(
                "UPDATE bookings SET status = 'cancelled', notes = ?, updated_at = ? WHERE id = ?",
                (updated_notes, now_iso, lookup_id),
            )
        else:
            conn.execute(
                """
                UPDATE bookings
                SET status = 'cancelled', cancellation_reason = ?, updated_at = ?
                WHERE booking_id = ?
                """,
                (reason, now_iso, lookup_id),
            )
        conn.commit()

    logger.info("[Booking DB] Cancelled booking_id=%s reason=%s", booking_id, reason)
    return json.dumps(
        {
            "status": "cancelled",
            "booking_id": booking_id,
            "reason": reason,
            "cancelled_at": now_iso,
            "message": f"Booking '{booking_id}' has been cancelled.",
        },
        indent=2,
    )


@tool
def get_daily_bookings(business_id: str, date: str) -> list:
    """Retrieve all bookings for a business on a specific date from SQLite.

    Args:
        business_id: Business ID (numeric string or integer).
        date: Target date in `YYYY-MM-DD` format.

    Returns:
        List of booking dictionaries ordered by `booking_time`.
    """
    biz_id = _normalize_business_id(business_id)
    with _get_db_connection() as conn:
        cols = _get_booking_schema(conn)
        time_col = "start_time" if "start_time" in cols else "booking_time"
        rows = conn.execute(
            f"""
            SELECT *
            FROM bookings
            WHERE business_id = ? AND booking_date = ?
            ORDER BY {time_col} ASC
            """,
            (biz_id, date),
        ).fetchall()

    results: List[Dict[str, Any]] = [dict(row) for row in rows]
    logger.info(
        "[Booking DB] Fetched %d bookings for business_id=%s date=%s",
        len(results),
        biz_id,
        date,
    )
    return results


@tool
def reschedule_booking(booking_id: str, new_date: str, new_time: str) -> str:
    """Reschedule an existing confirmed booking to a new date and time.

    Args:
        booking_id: Unique booking identifier.
        new_date: New appointment date (`YYYY-MM-DD`).
        new_time: New appointment time (`HH:MM`).

    Returns:
        JSON string confirming the updated appointment or conflict details.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    with _get_db_connection() as conn:
        cols = _get_booking_schema(conn)
        is_orm_schema = "start_time" in cols and "booking_id" not in cols
        id_col = "id" if is_orm_schema else "booking_id"
        time_col = "start_time" if is_orm_schema else "booking_time"
        lookup_id: Any = int(booking_id) if (is_orm_schema and str(booking_id).isdigit()) else booking_id

        row = conn.execute(
            f"SELECT * FROM bookings WHERE {id_col} = ?", (lookup_id,)
        ).fetchone()
        if not row:
            return json.dumps(
                {"status": "not_found", "message": f"Booking '{booking_id}' not found."}
            )
        if row["status"] == "cancelled":
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Cannot reschedule cancelled booking '{booking_id}'.",
                }
            )

        conflict = conn.execute(
            f"""
            SELECT {id_col} FROM bookings
            WHERE business_id = ? AND booking_date = ? AND {time_col} = ?
              AND status = 'confirmed' AND {id_col} != ?
            """,
            (row["business_id"], new_date, new_time, lookup_id),
        ).fetchone()
        if conflict:
            return json.dumps(
                {
                    "status": "conflict",
                    "message": f"Slot {new_time} on {new_date} is already booked.",
                }
            )

        conn.execute(
            f"""
            UPDATE bookings
            SET booking_date = ?, {time_col} = ?, updated_at = ?
            WHERE {id_col} = ?
            """,
            (new_date, new_time, now_iso, lookup_id),
        )
        conn.commit()

    logger.info(
        "[Booking DB] Rescheduled booking_id=%s to %s %s",
        booking_id,
        new_date,
        new_time,
    )
    return json.dumps(
        {
            "status": "rescheduled",
            "booking_id": booking_id,
            "new_date": new_date,
            "new_time": new_time,
            "updated_at": now_iso,
        },
        indent=2,
    )


@tool
def send_booking_confirmation(booking_id: str, channel: str = "email") -> str:
    """Send a booking confirmation notification (stub) for an existing booking.

    Args:
        booking_id: Unique booking identifier.
        channel: Notification channel (`email` or `sms`).

    Returns:
        JSON string confirming notification dispatch details.
    """
    with _get_db_connection() as conn:
        cols = _get_booking_schema(conn)
        is_orm_schema = "start_time" in cols and "booking_id" not in cols
        id_col = "id" if is_orm_schema else "booking_id"
        time_col = "start_time" if is_orm_schema else "booking_time"
        lookup_id: Any = int(booking_id) if (is_orm_schema and str(booking_id).isdigit()) else booking_id
        row = conn.execute(
            f"SELECT * FROM bookings WHERE {id_col} = ?", (lookup_id,)
        ).fetchone()

    if not row:
        return json.dumps(
            {"status": "not_found", "message": f"Booking '{booking_id}' not found."}
        )

    recipient = row["customer_email"] if channel == "email" else row["customer_phone"]
    logger.info(
        "[Booking Stub] Sent %s confirmation for booking_id=%s to %s",
        channel,
        booking_id,
        recipient or row["customer_name"],
    )
    return json.dumps(
        {
            "status": "sent",
            "mode": "stub",
            "channel": channel,
            "booking_id": booking_id,
            "customer_name": row["customer_name"],
            "recipient": recipient or "on_file",
            "appointment": f"{row['booking_date']} at {row[time_col]} ({row['service_name']})",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        },
        indent=2,
    )


class BookingTools:
    """Collection wrapper for Booking Management LangChain tools."""

    check_availability = check_availability
    create_booking = create_booking
    cancel_booking = cancel_booking
    get_daily_bookings = get_daily_bookings
    reschedule_booking = reschedule_booking
    send_booking_confirmation = send_booking_confirmation

    @classmethod
    def get_tools(cls) -> list:
        """Return all Booking Management tools as a list."""
        return [
            check_availability,
            create_booking,
            cancel_booking,
            get_daily_bookings,
            reschedule_booking,
            send_booking_confirmation,
        ]
