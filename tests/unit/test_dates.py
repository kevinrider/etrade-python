from datetime import UTC, date, datetime

import pytest

import etrade_python._dates as broker_dates
from etrade_python._dates import parse_broker_date, parse_broker_datetime


def test_parse_broker_datetime_from_epoch_milliseconds() -> None:
    assert parse_broker_datetime(1767225600000) == datetime(2026, 1, 1, tzinfo=UTC)


def test_parse_broker_datetime_from_epoch_seconds() -> None:
    assert parse_broker_datetime(1767225600) == datetime(2026, 1, 1, tzinfo=UTC)


def test_parse_broker_datetime_from_iso_zulu_string() -> None:
    assert parse_broker_datetime("2026-01-01T12:30:00Z") == datetime(2026, 1, 1, 12, 30, tzinfo=UTC)


def test_parse_broker_date_from_numeric_yyyymmdd() -> None:
    assert parse_broker_date(20261003) == date(2026, 10, 3)


def test_parse_broker_date_from_iso_date_string() -> None:
    assert parse_broker_date("2026-10-03") == date(2026, 10, 3)


def test_parse_broker_zero_and_blank_as_none() -> None:
    assert parse_broker_datetime(0) is None
    assert parse_broker_date("") is None


def test_parse_broker_datetime_from_etrade_quote_timestamp() -> None:
    assert parse_broker_datetime("15:17:00 EDT 06-20-2018") == datetime(
        2018, 6, 20, 19, 17, tzinfo=UTC
    )
    assert parse_broker_datetime("12:00:00 EST 01-01-2026") == datetime(2026, 1, 1, 17, tzinfo=UTC)


@pytest.mark.parametrize(
    "label, utc_hour",
    [
        ("EST", 17),
        ("EDT", 16),
        ("CST", 18),
        ("CDT", 17),
        ("MST", 19),
        ("MDT", 18),
        ("PST", 20),
        ("PDT", 19),
        ("UTC", 12),
        ("GMT", 12),
    ],
)
def test_quote_timezone_abbreviations_use_explicit_offset(label: str, utc_hour: int) -> None:
    for broker_date, month in [("01-01-2026", 1), ("07-01-2026", 7)]:
        assert parse_broker_datetime(f"12:00:00 {label} {broker_date}") == datetime(
            2026, month, 1, utc_hour, tzinfo=UTC
        )


@pytest.mark.parametrize(
    "offset, expected",
    [
        ("+0530", datetime(2026, 1, 1, 6, 30, tzinfo=UTC)),
        ("+05:30", datetime(2026, 1, 1, 6, 30, tzinfo=UTC)),
        ("-0730", datetime(2026, 1, 1, 19, 30, tzinfo=UTC)),
        ("-07:30", datetime(2026, 1, 1, 19, 30, tzinfo=UTC)),
        ("+0000", datetime(2026, 1, 1, 12, tzinfo=UTC)),
        ("-00:00", datetime(2026, 1, 1, 12, tzinfo=UTC)),
        ("+1400", datetime(2025, 12, 31, 22, tzinfo=UTC)),
        ("-1200", datetime(2026, 1, 2, tzinfo=UTC)),
    ],
)
def test_quote_numeric_timezone_offsets(offset: str, expected: datetime) -> None:
    assert parse_broker_datetime(f"12:00:00 {offset} 01-01-2026") == expected


def test_documented_pacific_quote_timestamp() -> None:
    assert parse_broker_datetime("15:15:43 PDT 03-21-2018") == datetime(
        2018, 3, 21, 22, 15, 43, tzinfo=UTC
    )


@pytest.mark.parametrize(
    "timezone", ["unknown-secret", "+2400", "-24:00", "+1260", "+5:30", "+050", "+05:30:00"]
)
def test_parse_broker_datetime_rejects_unsupported_quote_timezone(timezone: str) -> None:
    timestamp = f"15:15:43 {timezone} 03-21-2018"
    with pytest.raises(ValueError) as error:
        parse_broker_datetime(timestamp)
    assert str(error.value) == "Unsupported or invalid quote timestamp timezone"
    assert timestamp not in str(error.value)
    assert timezone not in str(error.value)


def test_parse_broker_datetime_from_native_datetime_and_date() -> None:
    naive = datetime(2026, 10, 3, 12, 30)
    aware = datetime(2026, 10, 3, 12, 30, tzinfo=UTC)

    assert parse_broker_datetime(naive) == aware
    assert parse_broker_datetime(date(2026, 10, 3)) == datetime(2026, 10, 3, tzinfo=UTC)


def test_parse_broker_datetime_from_compact_intraday_time(monkeypatch: pytest.MonkeyPatch) -> None:
    class FixedDate(date):
        @classmethod
        def today(cls) -> "FixedDate":
            return cls(2026, 10, 1)

    monkeypatch.setattr(broker_dates, "date", FixedDate)
    parsed = parse_broker_datetime(153000)

    assert parsed == datetime(2026, 10, 1, 15, 30, tzinfo=UTC)


def test_parse_broker_datetime_rejects_invalid_values() -> None:
    assert parse_broker_datetime(object()) is None
    assert parse_broker_datetime("not-a-date") is None
    assert parse_broker_datetime(20261340) is None
    assert parse_broker_datetime(999999) is None
    assert parse_broker_datetime("99:99:99 PST 01-01-2026") is None
    assert parse_broker_datetime("99:99:99 EDT 01-01-2026") is None
