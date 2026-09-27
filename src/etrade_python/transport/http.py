"""Shared async request pipeline. No business endpoint or OAuth logic lives here."""

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from decimal import Decimal
from typing import Literal
from urllib.parse import unquote

import httpx

from etrade_python.config import ETradeSettings
from etrade_python.exceptions import (
    AuthenticationRequired,
    AuthorizationExpired,
    ETradeAuthenticationError,
    ETradeTransportError,
    ETradeValidationError,
)
from etrade_python.transport.auth import RequestAuthenticator
from etrade_python.transport.logging import private_http_exchange
from etrade_python.transport.response import JsonValue, Redactor, TransportResponse, parse_response
from etrade_python.transport.retry import RetryPolicy, RetrySafety

LOGGER = logging.getLogger("etrade_python.transport")
HttpMethod = Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"]
QueryParameters = Mapping[str, str | int | bool | None]


def _decimal_json(value: object) -> str:
    if isinstance(value, Decimal) and value.is_finite():
        return str(value)
    raise ValueError("Unsupported JSON value")


class ApiTransport:
    """One shared HTTP client, with per-request authentication and retry state.

    Injected clients remain caller-owned. Their hooks and logging configuration
    are also caller-owned and must not record credentials or account information.
    """

    def __init__(
        self,
        settings: ETradeSettings,
        *,
        authenticator: RequestAuthenticator | None = None,
        http_client: httpx.AsyncClient | None = None,
        http_transport: httpx.AsyncBaseTransport | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if http_client is not None and http_transport is not None:
            raise ETradeValidationError("Supply either http_client or http_transport, not both")
        self._settings = settings
        self._authenticator = authenticator
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            transport=http_transport,
            timeout=settings.request_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        )
        self._retry_policy = retry_policy or RetryPolicy()
        self._sleep = sleep
        self._closed = False

    async def __aenter__(self) -> "ApiTransport":
        if self._closed:
            raise ETradeTransportError("Transport is closed")
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if not self._closed:
            self._closed = True
            if self._owns_client:
                await self._client.aclose()

    async def request(
        self,
        method: HttpMethod,
        path: str,
        *,
        params: QueryParameters | None = None,
        body: JsonValue = None,
        safety: RetrySafety = RetrySafety.NEVER,
        operation: str = "request",
    ) -> TransportResponse:
        """Request an API-relative JSON endpoint.

        `operation` is a static label such as `accounts.list`, never user data.
        `path` includes /v1 and any desired .json suffix. Query parameters must be
        passed separately. Decimal request values serialize as JSON strings.
        """
        if self._closed:
            raise ETradeTransportError("Transport is closed")
        self._validate_path(path)
        if not re.fullmatch(r"[a-z_]+(?:\.[a-z_]+)*", operation):
            raise ETradeValidationError("Invalid operation label")
        if method not in {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"}:
            raise ETradeValidationError("Invalid HTTP method")
        if safety is RetrySafety.SAFE_READ and method not in {"GET", "HEAD"}:
            raise ETradeValidationError("Only read requests may be classified as safe reads")
        if self._authenticator is None:
            raise AuthenticationRequired(
                "An authenticator is required; OAuth is not implemented yet"
            )
        try:
            content = (
                json.dumps(body, default=_decimal_json, allow_nan=False).encode()
                if body is not None
                else None
            )
        except (ValueError, TypeError, RecursionError):
            raise ETradeValidationError("Invalid JSON request body") from None
        headers = {"Accept": "application/json", "User-Agent": "etrade-python/0.1.0.dev0"}
        if content is not None:
            headers["Content-Type"] = "application/json"
        url = self._settings.environment.api_base_url + path
        attempt = 0
        while True:
            attempt += 1
            try:
                request = self._client.build_request(
                    method,
                    url,
                    params={k: v for k, v in (params or {}).items() if v is not None},
                    content=content,
                    headers=headers,
                    timeout=self._settings.request_timeout_seconds,
                )
            except (httpx.HTTPError, ValueError, TypeError):
                raise ETradeValidationError("Could not construct HTTP request") from None
            original_url, original_content = request.url, request.content
            try:
                await self._authenticator.authenticate(request)
            except AuthenticationRequired:
                raise AuthenticationRequired("Authorization is required") from None
            except AuthorizationExpired:
                raise AuthorizationExpired("Authorization has expired") from None
            except Exception:
                raise ETradeAuthenticationError("Request authentication failed") from None
            if (
                request.method != method
                or request.url != original_url
                or request.content != original_content
            ):
                raise ETradeAuthenticationError(
                    "Authenticator changed the request method, URL, or body"
                )
            redactor = self._redactor(request)
            started = time.monotonic()
            try:
                with private_http_exchange():
                    response = await self._client.send(request, follow_redirects=False, auth=None)
            except httpx.TransportError as exc:
                self._log(operation, attempt, started, None)
                delay = self._retry_policy.delay(safety=safety, attempt=attempt, error=exc)
                if delay is None:
                    raise ETradeTransportError(
                        "HTTP exchange failed; the outcome of a mutation may be unknown"
                    ) from None
                await self._sleep(delay)
                continue
            except httpx.HTTPError:
                raise ETradeTransportError("HTTP exchange failed") from None
            self._log(operation, attempt, started, response.status_code)
            delay = self._retry_policy.delay(safety=safety, attempt=attempt, response=response)
            if delay is not None:
                await response.aclose()
                await self._sleep(delay)
                continue
            try:
                return parse_response(response, redactor)
            finally:
                await response.aclose()

    @staticmethod
    def _validate_path(path: str) -> None:
        decoded = unquote(path)
        if (
            not path.startswith("/v1/")
            or any(c in decoded for c in ("?", "#", "\\", "%"))
            or "//" in decoded
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in decoded)
            or any(part in {".", ".."} for part in decoded.split("/"))
        ):
            raise ETradeValidationError(
                "Expected a relative /v1/ API path without query or traversal"
            )

    def _redactor(self, request: httpx.Request) -> Redactor:
        secrets = [
            self._settings.consumer_key.get_secret_value(),
            self._settings.consumer_secret.get_secret_value(),
        ]
        authorization = request.headers.get("authorization", "")
        secrets.append(authorization)
        # OAuth header values may be percent encoded. Include both representations.
        secrets.extend(re.findall(r'="([^"\r\n]*)"', authorization))
        if authorization and not authorization.startswith("OAuth "):
            secrets.append(authorization.split(" ", 1)[-1])
        secrets.extend(str(value) for value in request.url.params.values())
        segments = request.url.path.split("/")
        if "accounts" in segments:
            index = segments.index("accounts") + 1
            if index < len(segments) and segments[index] != "list.json":
                secrets.append(segments[index])
        return Redactor(secrets)

    def _log(self, operation: str, attempt: int, started: float, status: int | None) -> None:
        LOGGER.info(
            "E*TRADE HTTP attempt",
            extra={
                "operation": operation,
                "environment": self._settings.environment.value,
                "status_code": status,
                "latency_seconds": time.monotonic() - started,
                "attempt": attempt,
            },
        )
