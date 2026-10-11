"""JSON decoding and deliberately small, defensive broker error parsing."""

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import NoReturn, TypeAlias, TypeVar, cast
from urllib.parse import quote, quote_plus, unquote
from xml.etree import ElementTree

import httpx
from pydantic import BaseModel

from etrade_python.exceptions import (
    ETradeApiError,
    ETradeHttpAuthenticationError,
    ETradeNotFoundError,
    ETradeRateLimitError,
    ETradeResponseError,
    ETradeUnavailableError,
)

JsonValue: TypeAlias = "None | bool | int | Decimal | str | list[JsonValue] | dict[str, JsonValue]"


ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


def validate_response_shape(
    model: ResponseModel, response_name: str, *, collection_field: str | None = None
) -> ResponseModel:
    """Check parsed HTTP data without changing direct model construction."""
    if collection_field is not None and collection_field not in model.model_fields_set:
        raise ETradeResponseError(f"Invalid {response_name} response: missing collection")
    _validate_populated_model(model, response_name, "")
    return model


def _validate_populated_model(model: BaseModel, response_name: str, path: str) -> None:
    populated = [
        name
        for name in type(model).model_fields
        if name in model.model_fields_set and getattr(model, name) is not None
    ]
    if not populated:
        location = f" at {path}" if path else ""
        raise ETradeResponseError(
            f"Invalid {response_name} response: unrecognized object{location}"
        )
    for name in populated:
        value = getattr(model, name)
        field_path = f"{path}.{name}" if path else name
        if isinstance(value, BaseModel):
            _validate_populated_model(value, response_name, field_path)
        elif isinstance(value, list):
            for index, item in enumerate(cast(list[object], value)):
                if isinstance(item, BaseModel):
                    _validate_populated_model(item, response_name, f"{field_path}.{index}")


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


def response_diagnostic(response: httpx.Response, redactor: Redactor) -> str:
    """Return a short sanitized response summary for parser diagnostics."""
    content_type = response.headers.get("content-type", "<missing>").split(";", 1)[0].strip()
    content_length = len(response.content)
    preview = _body_preview(response.content, redactor)
    parts = [
        f"status={response.status_code}",
        f"content_type={content_type or '<missing>'}",
        f"bytes={content_length}",
    ]
    if preview:
        parts.append(f"body_preview={preview}")
    return ", ".join(parts)


def validation_diagnostic(error: object, *, prefix: str | None = None) -> str:
    """Return sanitized Pydantic validation locations without rejected values."""
    errors = getattr(error, "errors", None)
    if not callable(errors):
        return "validation failed"
    paths: list[str] = []
    raw_errors = cast(list[dict[str, object]], errors())
    for item in raw_errors:
        loc = item.get("loc")
        if not isinstance(loc, tuple) or not loc:
            continue
        location = cast(tuple[object, ...], loc)
        rendered = ".".join(str(part) for part in location)
        if prefix:
            rendered = f"{prefix}.{rendered}"
        paths.append(rendered)
    if not paths:
        return "validation failed"
    unique_paths = list(dict.fromkeys(paths))
    if len(unique_paths) > 5:
        return "; ".join(unique_paths[:5]) + f"; +{len(unique_paths) - 5} more"
    return "; ".join(unique_paths)


def raise_response_validation_error(
    message: str, error: object, *, prefix: str | None = None
) -> NoReturn:
    """Raise a sanitized response validation error from a model parser failure."""
    diagnostic = validation_diagnostic(error, prefix=prefix)
    raise ETradeResponseError(f"{message}: {diagnostic}") from None


def _body_preview(content: bytes, redactor: Redactor) -> str | None:
    if not content:
        return None
    preview = content[:300].decode("utf-8", errors="replace")
    cleaned = redactor.clean(preview)
    if len(content) > 300:
        cleaned = f"{cleaned}..."
    return cleaned


def parse_response(response: httpx.Response, redactor: Redactor) -> TransportResponse:
    request_id = correlation_id(response, redactor)
    if response.status_code == 204:
        return TransportResponse(204, None, request_id)
    if not 200 <= response.status_code < 300:
        raise api_error(response, redactor)
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json" and not content_type.endswith("+json"):
        raise ETradeResponseError(
            f"Expected a JSON response ({response_diagnostic(response, redactor)})",
            status_code=response.status_code,
            request_id=request_id,
        )
    try:
        data = decode_json(response.content)
    except (ValueError, UnicodeError, RecursionError):
        raise ETradeResponseError(
            f"Invalid JSON response ({response_diagnostic(response, redactor)})",
            status_code=response.status_code,
            request_id=request_id,
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
