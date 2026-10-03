"""Internal helpers for parsing broker date/time values."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo


def parse_broker_datetime(value: Any) -> datetime | None:
    """Parse an E*TRADE date/time value into a timezone-aware datetime.

    E*TRADE responses commonly encode date/time fields as epoch milliseconds,
    epoch seconds, or compact numeric dates. This mirrors the Carbon casting
    behavior used by laravel-etrade for DTO properties typed as Carbon.
    """
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        return _ensure_timezone(value)

    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)

    if isinstance(value, int | float):
        return _parse_numeric_datetime(value)

    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None
        if _is_numeric_string(trimmed):
            return _parse_numeric_datetime(int(trimmed))
        return _parse_string_datetime(trimmed)

    return None


def parse_broker_date(value: Any) -> date | None:
    """Parse an E*TRADE date/time value into a date."""
    parsed = parse_broker_datetime(value)
    if parsed is None:
        return None
    return parsed.date()


def _parse_numeric_datetime(value: int | float) -> datetime | None:
    integer = int(value)
    if integer == 0:
        return None

    digits = str(abs(integer))
    length = len(digits)

    if length >= 13:
        return datetime.fromtimestamp(integer / 1000, tz=UTC)

    if length == 8:
        try:
            parsed_date = datetime.strptime(digits, "%Y%m%d").date()
        except ValueError:
            return None
        return datetime.combine(parsed_date, time.min, tzinfo=UTC)

    if length in {4, 6}:
        time_format = "%H%M%S" if length == 6 else "%H%M"
        try:
            parsed_time = datetime.strptime(digits, time_format).time()
        except ValueError:
            return None
        return datetime.combine(date.today(), parsed_time, tzinfo=UTC)

    return datetime.fromtimestamp(integer, tz=UTC)


def _parse_string_datetime(value: str) -> datetime | None:
    for candidate in _string_datetime_candidates(value):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        return _ensure_timezone(parsed)

    quote_datetime = _parse_quote_datetime(value)
    if quote_datetime is not None:
        return quote_datetime

    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        return _ensure_timezone(parsed)

    return None


def _parse_quote_datetime(value: str) -> datetime | None:
    parts = value.split()
    if len(parts) != 3 or parts[1] not in {"EST", "EDT"}:
        return None
    try:
        parsed = datetime.strptime(f"{parts[0]} {parts[2]}", "%H:%M:%S %m-%d-%Y")
    except ValueError:
        return None
    return parsed.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)


def _string_datetime_candidates(value: str) -> tuple[str, ...]:
    if value.endswith("Z"):
        return (value[:-1] + "+00:00", value)
    return (value,)


def _ensure_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _is_numeric_string(value: str) -> bool:
    return value.isdecimal() or (value.startswith("-") and value[1:].isdecimal())
