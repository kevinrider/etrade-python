"""JSON decoding and deliberately small, defensive broker error parsing."""

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TypeAlias, cast
from urllib.parse import quote, quote_plus, unquote
from xml.etree import ElementTree

import httpx

from etrade_python.exceptions import (
    ETradeApiError,
    ETradeHttpAuthenticationError,
    ETradeNotFoundError,
    ETradeRateLimitError,
    ETradeResponseError,
    ETradeUnavailableError,
)

JsonValue: TypeAlias = "None | bool | int | Decimal | str | list[JsonValue] | dict[str, JsonValue]"


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    data: JsonValue = field(repr=False)
    request_id: str | None = None


class Redactor:
    """Request-local redaction; never retain credentials in diagnostics."""

    def __init__(self, secrets: list[str]) -> None:
        variants: set[str] = set()
        for secret in secrets:
            if secret:
                variants.update(
                    (secret, quote(secret, safe=""), quote_plus(secret), unquote(secret))
                )
        self._secrets = sorted(variants, key=len, reverse=True)

    def __repr__(self) -> str:
        return "Redactor()"

    def clean(self, value: str) -> str:
        for secret in self._secrets:
            value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(?i)\bOAuth\s+[^\r\n]+", "[REDACTED]", value)
        value = re.sub(
            r"(?i)((?:oauth_)?(?:token(?:_secret)?|consumer_secret|verifier|signature)"
            r"\s*[=:]\s*)[^\s,;&]+",
            r"\1[REDACTED]",
            value,
        )
        return " ".join(value.split())[:1000]


def _invalid_constant(value: str) -> None:
    raise ValueError("Non-finite JSON number")


def decode_json(content: bytes) -> JsonValue:
    return cast(
        JsonValue, json.loads(content, parse_float=Decimal, parse_constant=_invalid_constant)
    )


def correlation_id(response: httpx.Response, redactor: Redactor) -> str | None:
    for name in ("x-request-id", "x-correlation-id"):
        if value := response.headers.get(name):
            return redactor.clean(value)
    return None


def parse_response(response: httpx.Response, redactor: Redactor) -> TransportResponse:
    request_id = correlation_id(response, redactor)
    if response.status_code == 204:
        return TransportResponse(204, None, request_id)
    if not 200 <= response.status_code < 300:
        raise api_error(response, redactor)
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json" and not content_type.endswith("+json"):
        raise ETradeResponseError("Expected a JSON response", status_code=response.status_code)
    try:
        data = decode_json(response.content)
    except (ValueError, UnicodeError, RecursionError):
        raise ETradeResponseError(
            "Invalid JSON response", status_code=response.status_code, request_id=request_id
        ) from None
    return TransportResponse(response.status_code, data, request_id)


def _error_fields(content: bytes) -> tuple[str | None, str | None]:
    # Error payloads are never exposed wholesale. Refuse large or entity-bearing XML.
    if len(content) > 65536:
        return None, None
    try:
        data = decode_json(content)
        if isinstance(data, dict):
            error = data.get("Error", data)
            if isinstance(error, dict):
                code = error.get("code")
                message = error.get("message")
                return (
                    str(code) if isinstance(code, (str, int)) else None,
                    message if isinstance(message, str) else None,
                )
    except (ValueError, UnicodeError, RecursionError):
        pass
    if b"<!" in content or b"\x00" in content:
        return None, None
    try:
        root = ElementTree.fromstring(content)
        if root.tag.rsplit("}", 1)[-1] != "Error":
            return None, None
        fields = {node.tag.rsplit("}", 1)[-1]: node.text for node in root}
        return fields.get("code"), fields.get("message")
    except ElementTree.ParseError:
        return None, None


def api_error(response: httpx.Response, redactor: Redactor) -> ETradeApiError:
    code, message = _error_fields(response.content)
    code = redactor.clean(code) if code else None
    message = redactor.clean(message) if message else None
    error_type: type[ETradeApiError] = ETradeApiError
    status = response.status_code
    if status in {401, 403}:
        error_type = ETradeHttpAuthenticationError
    elif status == 404:
        error_type = ETradeNotFoundError
    elif status == 429:
        error_type = ETradeRateLimitError
    elif status >= 500:
        error_type = ETradeUnavailableError
    return error_type(
        f"E*TRADE request failed (HTTP {status})",
        status_code=status,
        broker_code=code,
        broker_message=message,
        request_id=correlation_id(response, redactor),
    )
