"""OAuth 1.0a protocol operations for E*TRADE."""

import base64
import hashlib
import hmac
import logging
import re
import secrets
import time
from collections.abc import Callable
from typing import Final
from urllib.parse import parse_qsl, quote, urlencode

import httpx
from pydantic import SecretStr

from etrade_python.auth.credentials import (
    AuthorizationUrl,
    ETradeCredentials,
    RenewalResult,
    RequestToken,
    RevocationResult,
)
from etrade_python.config import ETradeSettings
from etrade_python.enums import AUTHORIZATION_URL, OAUTH_BASE_URL
from etrade_python.exceptions import (
    ETradeResponseError,
    ETradeTransportError,
    ETradeValidationError,
)
from etrade_python.transport.logging import private_http_exchange
from etrade_python.transport.response import Redactor, parse_response

LOGGER = logging.getLogger("etrade_python.auth.oauth")
SIGNATURE_METHOD: Final[str] = "HMAC-SHA1"


def _encode(value: str) -> str:
    return quote(value, safe="~-._")


def _base_url(url: httpx.URL) -> str:
    scheme = url.scheme.lower()
    host = (url.host or "").lower()
    port = url.port
    authority = host
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        authority = f"{authority}:{port}"
    path = url.raw_path.decode("ascii").split("?", 1)[0] or "/"
    return f"{scheme}://{authority}{path}"


def _authorization_header(parameters: dict[str, str]) -> str:
    header = ",".join(
        f'{_encode(key)}="{_encode(value)}"' for key, value in sorted(parameters.items())
    )
    return f'OAuth realm="",{header}'


class OAuthClient:
    """Protocol-level OAuth operations and request signing."""

    def __init__(
        self,
        settings: ETradeSettings,
        *,
        http_client: httpx.AsyncClient | None = None,
        http_transport: httpx.AsyncBaseTransport | None = None,
        nonce_factory: Callable[[], str] | None = None,
        timestamp_factory: Callable[[], int] | None = None,
    ) -> None:
        if http_client is not None and http_transport is not None:
            raise ETradeValidationError("Supply either http_client or http_transport, not both")
        self._settings = settings
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            transport=http_transport,
            timeout=settings.request_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        )
        self._nonce_factory = nonce_factory or (lambda: secrets.token_hex(16))
        self._timestamp_factory = timestamp_factory or (lambda: int(time.time()))
        self._closed = False

    async def __aenter__(self) -> "OAuthClient":
        if self._closed:
            raise ETradeTransportError("OAuth client is closed")
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if not self._closed:
            self._closed = True
            if self._owns_client:
                await self._client.aclose()

    async def get_request_token(self) -> RequestToken:
        request = self._signed_get(
            f"{OAUTH_BASE_URL}/oauth/request_token",
            oauth_parameters={"oauth_callback": "oob"},
        )
        text = await self._send(request, operation="oauth.request_token")
        values = self._parse_form(text)
        try:
            return RequestToken(
                oauth_token=SecretStr(values["oauth_token"]),
                oauth_token_secret=SecretStr(values["oauth_token_secret"]),
                oauth_callback_confirmed=values.get("oauth_callback_confirmed", "").lower()
                == "true",
            )
        except KeyError:
            raise ETradeResponseError("Invalid OAuth request-token response") from None

    def get_authorization_url(self, request_token: RequestToken) -> AuthorizationUrl:
        query = urlencode(
            {
                "key": self._settings.consumer_key.get_secret_value(),
                "token": request_token.oauth_token.get_secret_value(),
            }
        )
        return AuthorizationUrl(url=f"{AUTHORIZATION_URL}?{query}", request_token=request_token)

    async def exchange_verifier(
        self, request_token: RequestToken, verifier: str
    ) -> ETradeCredentials:
        if not verifier.strip():
            raise ETradeValidationError("OAuth verifier is required")
        request = self._signed_get(
            f"{OAUTH_BASE_URL}/oauth/access_token",
            token=request_token.oauth_token,
            token_secret=request_token.oauth_token_secret,
            oauth_parameters={"oauth_verifier": verifier},
        )
        text = await self._send(request, operation="oauth.access_token")
        values = self._parse_form(text)
        try:
            return ETradeCredentials(
                access_token=SecretStr(values["oauth_token"]),
                access_token_secret=SecretStr(values["oauth_token_secret"]),
            )
        except KeyError:
            raise ETradeResponseError("Invalid OAuth access-token response") from None

    async def renew_access_token(self, credentials: ETradeCredentials) -> RenewalResult:
        request = self._signed_get(
            f"{OAUTH_BASE_URL}/oauth/renew_access_token",
            token=credentials.access_token,
            token_secret=credentials.access_token_secret,
        )
        text = await self._send(request, operation="oauth.renew_access_token")
        return RenewalResult(credentials=credentials, message=text.strip())

    async def revoke_access_token(self, credentials: ETradeCredentials) -> RevocationResult:
        request = self._signed_get(
            f"{OAUTH_BASE_URL}/oauth/revoke_access_token",
            token=credentials.access_token,
            token_secret=credentials.access_token_secret,
        )
        text = await self._send(request, operation="oauth.revoke_access_token")
        return RevocationResult(revoked=True, message=text.strip())

    def sign_request(self, request: httpx.Request, credentials: ETradeCredentials) -> None:
        parameters = self._oauth_parameters(token=credentials.access_token)
        signature = self._signature(
            request.method,
            request.url,
            parameters,
            token_secret=credentials.access_token_secret,
        )
        parameters["oauth_signature"] = signature
        request.headers["Authorization"] = _authorization_header(parameters)

    def _signed_get(
        self,
        url: str,
        *,
        token: SecretStr | None = None,
        token_secret: SecretStr | None = None,
        oauth_parameters: dict[str, str] | None = None,
    ) -> httpx.Request:
        request = self._client.build_request(
            "GET", url, timeout=self._settings.request_timeout_seconds
        )
        parameters = self._oauth_parameters(token=token)
        parameters.update(oauth_parameters or {})
        signature = self._signature("GET", request.url, parameters, token_secret=token_secret)
        parameters["oauth_signature"] = signature
        request.headers["Authorization"] = _authorization_header(parameters)
        return request

    def _oauth_parameters(self, *, token: SecretStr | None = None) -> dict[str, str]:
        parameters = {
            "oauth_consumer_key": self._settings.consumer_key.get_secret_value(),
            "oauth_nonce": self._nonce_factory(),
            "oauth_signature_method": SIGNATURE_METHOD,
            "oauth_timestamp": str(self._timestamp_factory()),
        }
        if token is not None:
            parameters["oauth_token"] = token.get_secret_value()
        return parameters

    def _signature(
        self,
        method: str,
        url: httpx.URL,
        oauth_parameters: dict[str, str],
        *,
        token_secret: SecretStr | None,
    ) -> str:
        parameters = [
            (key, value) for key, value in oauth_parameters.items() if key != "oauth_signature"
        ]
        parameters.extend((key, value) for key, value in url.params.multi_items())
        parameter_string = "&".join(
            f"{_encode(key)}={_encode(value)}" for key, value in sorted(parameters)
        )
        base_string = "&".join(
            [_encode(method.upper()), _encode(_base_url(url)), _encode(parameter_string)]
        )
        secret = self._settings.consumer_secret.get_secret_value()
        token_secret_value = "" if token_secret is None else token_secret.get_secret_value()
        signing_key = f"{_encode(secret)}&{_encode(token_secret_value)}"
        digest = hmac.new(
            signing_key.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha1
        ).digest()
        return base64.b64encode(digest).decode("ascii")

    async def _send(self, request: httpx.Request, *, operation: str) -> str:
        if self._closed:
            raise ETradeTransportError("OAuth client is closed")
        redactor = self._redactor(request)
        try:
            with private_http_exchange():
                response = await self._client.send(request, follow_redirects=False, auth=None)
        except httpx.TransportError:
            raise ETradeTransportError("OAuth HTTP exchange failed") from None
        except httpx.HTTPError:
            raise ETradeTransportError("OAuth HTTP exchange failed") from None
        try:
            if response.status_code >= 400:
                parse_response(response, redactor)
            LOGGER.info("E*TRADE OAuth request", extra={"operation": operation})
            return response.text
        finally:
            await response.aclose()

    @staticmethod
    def _parse_form(text: str) -> dict[str, str]:
        values = dict(parse_qsl(text, keep_blank_values=True, strict_parsing=False))
        if not values:
            raise ETradeResponseError("Invalid OAuth form response")
        return values

    def _redactor(self, request: httpx.Request) -> Redactor:
        authorization = request.headers.get("authorization", "")
        secrets_to_mask = [
            self._settings.consumer_key.get_secret_value(),
            self._settings.consumer_secret.get_secret_value(),
            authorization,
        ]
        # Redactor also masks decoded forms of percent-encoded OAuth values.
        secrets_to_mask.extend(re.findall(r'="([^"\r\n]*)"', authorization))
        return Redactor(secrets_to_mask)
