from datetime import UTC, date, datetime

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


def test_parse_broker_datetime_from_native_datetime_and_date() -> None:
    naive = datetime(2026, 10, 3, 12, 30)
    aware = datetime(2026, 10, 3, 12, 30, tzinfo=UTC)

    assert parse_broker_datetime(naive) == aware
    assert parse_broker_datetime(date(2026, 10, 3)) == datetime(2026, 10, 3, tzinfo=UTC)


def test_parse_broker_datetime_from_compact_intraday_time() -> None:
    parsed = parse_broker_datetime(153000)

    assert parsed is not None
    assert parsed.hour == 15
    assert parsed.minute == 30
    assert parsed.second == 0
    assert parsed.tzinfo == UTC


def test_parse_broker_datetime_rejects_invalid_values() -> None:
    assert parse_broker_datetime(object()) is None
    assert parse_broker_datetime("not-a-date") is None
    assert parse_broker_datetime(20261340) is None
    assert parse_broker_datetime(999999) is None
    assert parse_broker_datetime("12:00:00 PST 01-01-2026") is None
    assert parse_broker_datetime("99:99:99 EDT 01-01-2026") is None
