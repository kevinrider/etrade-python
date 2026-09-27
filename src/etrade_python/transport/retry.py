"""Explicit retry classification; HTTP verbs alone never establish safety."""

import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum

import httpx

from etrade_python.exceptions import ETradeValidationError


class RetrySafety(StrEnum):
    NEVER = "never"
    SAFE_READ = "safe_read"


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 30.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_attempts, bool)
            or type(self.max_attempts) is not int
            or self.max_attempts < 1
            or not math.isfinite(self.base_delay_seconds)
            or not math.isfinite(self.max_delay_seconds)
            or self.base_delay_seconds < 0
            or self.max_delay_seconds < self.base_delay_seconds
        ):
            raise ETradeValidationError("Invalid retry policy")

    def delay(
        self,
        *,
        safety: RetrySafety,
        attempt: int,
        response: httpx.Response | None = None,
        error: httpx.TransportError | None = None,
        now: datetime | None = None,
    ) -> float | None:
        """Return a delay or None. Attempt numbering starts at one."""
        if safety is not RetrySafety.SAFE_READ or attempt >= self.max_attempts:
            return None
        transient = isinstance(error, (httpx.ConnectError, httpx.TimeoutException))
        if response is not None:
            transient = response.status_code in {429, 502, 503, 504}
        if not transient:
            return None
        if response is not None and (header := response.headers.get("retry-after")):
            wait = self._retry_after(header, now or datetime.now(UTC))
            if wait is not None:
                return wait if wait <= self.max_delay_seconds else None
        ceiling = min(self.max_delay_seconds, self.base_delay_seconds * 2 ** min(attempt - 1, 30))
        return random.uniform(0, ceiling)

    @staticmethod
    def _retry_after(value: str, now: datetime) -> float | None:
        if value.isascii() and value.isdecimal():
            try:
                return float(int(value))
            except (ValueError, OverflowError):
                return math.inf
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                return None
            return max(0.0, (parsed - now).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None
