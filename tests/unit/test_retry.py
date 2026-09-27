from datetime import UTC, datetime

import httpx
import pytest

from etrade_python import ETradeValidationError
from etrade_python.transport import RetryPolicy, RetrySafety


@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_transient_status(status: int) -> None:
    policy = RetryPolicy()
    delay = policy.delay(safety=RetrySafety.SAFE_READ, attempt=1, response=httpx.Response(status))
    assert delay is not None and 0 <= delay <= 0.5
    assert (
        policy.delay(safety=RetrySafety.NEVER, attempt=1, response=httpx.Response(status)) is None
    )
    assert (
        policy.delay(safety=RetrySafety.SAFE_READ, attempt=3, response=httpx.Response(status))
        is None
    )


@pytest.mark.parametrize("status", [200, 204, 301, 400, 401, 403, 404, 500, 501])
def test_non_retry_status(status: int) -> None:
    assert (
        RetryPolicy().delay(
            safety=RetrySafety.SAFE_READ, attempt=1, response=httpx.Response(status)
        )
        is None
    )


@pytest.mark.parametrize(
    "error", [httpx.ConnectError("x"), httpx.ReadTimeout("x"), httpx.ConnectTimeout("x")]
)
def test_transient_exceptions(error: httpx.TransportError) -> None:
    assert RetryPolicy().delay(safety=RetrySafety.SAFE_READ, attempt=1, error=error) is not None


def test_non_retry_exception() -> None:
    assert (
        RetryPolicy().delay(
            safety=RetrySafety.SAFE_READ, attempt=1, error=httpx.RemoteProtocolError("x")
        )
        is None
    )


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("10", 10),
        ("31", None),
        ("Wed, 01 Jan 2025 00:00:15 GMT", 15),
        ("Tue, 31 Dec 2024 23:59:59 GMT", 0),
        ("9" * 5000, None),
    ],
)
def test_retry_after(header: str, expected: float | None) -> None:
    assert (
        RetryPolicy().delay(
            safety=RetrySafety.SAFE_READ,
            attempt=1,
            response=httpx.Response(429, headers={"Retry-After": header}),
            now=datetime(2025, 1, 1, tzinfo=UTC),
        )
        == expected
    )


@pytest.mark.parametrize("header", ["invalid", "-1", "inf", "Wed, 01 Jan 2025 00:00:15"])
def test_invalid_retry_after_falls_back(header: str) -> None:
    delay = RetryPolicy().delay(
        safety=RetrySafety.SAFE_READ,
        attempt=1,
        response=httpx.Response(503, headers={"Retry-After": header}),
    )
    assert delay is not None and 0 <= delay <= 0.5


@pytest.mark.parametrize(
    "values",
    [
        {"max_attempts": 0},
        {"max_attempts": True},
        {"max_attempts": 1.5},
        {"base_delay_seconds": -1},
        {"base_delay_seconds": float("nan")},
        {"max_delay_seconds": float("inf")},
        {"max_delay_seconds": 0.1},
    ],
)
def test_invalid_retry_policy(values: dict[str, object]) -> None:
    with pytest.raises(ETradeValidationError):
        RetryPolicy(**values)  # pyright: ignore[reportArgumentType]
