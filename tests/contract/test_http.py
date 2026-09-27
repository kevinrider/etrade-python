import asyncio
import logging
import traceback
from decimal import Decimal
from typing import cast

import httpx
import pytest

from etrade_python import (
    AuthenticationRequired,
    AuthorizationExpired,
    ETradeApiError,
    ETradeAuthenticationError,
    ETradeSettings,
    ETradeTransportError,
    ETradeValidationError,
)
from etrade_python.transport import ApiTransport, RetryPolicy, RetrySafety
from etrade_python.transport.http import HttpMethod
from tests.conftest import FakeAuthenticator


async def test_request_contract(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.host == "apisb.etrade.com"
        assert request.url.path == "/v1/example.json"
        assert request.url.params == httpx.QueryParams({"q": "a & b", "flag": "true"})
        assert request.headers["Accept"] == "application/json"
        assert request.headers["Content-Type"] == "application/json"
        assert request.headers["Authorization"].startswith("OAuth ")
        assert request.content == b'{"amount": "1.234567890123456789"}'
        assert request.extensions["timeout"] == dict.fromkeys(
            ["connect", "read", "write", "pool"], 30
        )
        return httpx.Response(200, json={"result": "ok"})

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as api:
        response = await api.request(
            "POST",
            "/v1/example.json",
            params={"q": "a & b", "flag": True, "omit": None},
            body={"amount": Decimal("1.234567890123456789")},
        )
        assert response.data == {"result": "ok"}
    assert auth.calls == 1


async def test_production_host(auth: FakeAuthenticator) -> None:
    settings = ETradeSettings(
        consumer_key="fake-key", consumer_secret="fake-secret", environment="production"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.etrade.com"
        return httpx.Response(204)

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as api:
        assert (await api.request("GET", "/v1/example")).data is None


async def test_missing_auth_and_closed(settings: ETradeSettings) -> None:
    async with ApiTransport(settings) as api:
        with pytest.raises(AuthenticationRequired):
            await api.request("GET", "/v1/example")
    with pytest.raises(ETradeTransportError, match="closed"):
        await api.request("GET", "/v1/example")


@pytest.mark.parametrize(
    "path",
    [
        "https://evil.example/v1/x",
        "//evil.example/x",
        "/oauth/x",
        "/v1/../x",
        "/v1/%2e%2e/x",
        "/v1/%252e%252e/x",
        "/v1/x?q=secret",
        "/v1/x#fragment",
        "/v1/a\\b",
        "/v1/a//b",
        "/v1/a b",
        "/v1/a\n",
        "/v1/a%00",
    ],
)
async def test_reject_unsafe_paths(settings: ETradeSettings, path: str) -> None:
    async with ApiTransport(settings) as api:
        with pytest.raises(ETradeValidationError):
            await api.request("GET", path)


async def test_invalid_operation_and_method(settings: ETradeSettings) -> None:
    async with ApiTransport(settings) as api:
        with pytest.raises(ETradeValidationError, match="operation"):
            await api.request("GET", "/v1/x", operation="account-secret-123")
        with pytest.raises(ETradeValidationError, match="method"):
            await api.request(cast(HttpMethod, "BOGUS"), "/v1/x")
        with pytest.raises(ETradeValidationError, match="Only read"):
            await api.request("POST", "/v1/x", safety=RetrySafety.SAFE_READ)


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity")])
async def test_invalid_body(
    settings: ETradeSettings, auth: FakeAuthenticator, value: Decimal
) -> None:
    async with ApiTransport(settings, authenticator=auth) as api:
        with pytest.raises(ETradeValidationError, match="JSON"):
            await api.request("POST", "/v1/x", body={"value": value})


@pytest.mark.parametrize("mode", ["missing", "expired", "unexpected", "url", "body", "method"])
async def test_auth_failures(settings: ETradeSettings, mode: str) -> None:
    class BadAuth:
        async def authenticate(self, request: httpx.Request) -> None:
            if mode == "missing":
                raise AuthenticationRequired("fake-secret")
            if mode == "expired":
                raise AuthorizationExpired("fake-secret")
            if mode == "unexpected":
                raise ValueError("fake-secret")
            if mode == "url":
                request.url = httpx.URL("https://evil.example")
            elif mode == "method":
                request.method = "POST"
            else:
                request.read()
                request._content = b"changed"  # pyright: ignore[reportPrivateUsage]

    expected = {"missing": AuthenticationRequired, "expired": AuthorizationExpired}.get(
        mode, ETradeAuthenticationError
    )
    async with ApiTransport(settings, authenticator=BadAuth()) as api:
        with pytest.raises(expected) as exc:
            await api.request("GET", "/v1/x")
    assert "fake-secret" not in "".join(traceback.format_exception(exc.value))


async def test_safe_read_retries_and_resigns(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    requests: list[httpx.Request] = []
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ConnectError("fake-secret")
        if len(requests) == 2:
            return httpx.Response(503, headers={"Retry-After": "2"})
        return httpx.Response(200, json={"ok": True})

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler), sleep=sleep
    ) as api:
        assert (await api.request("GET", "/v1/x", safety=RetrySafety.SAFE_READ)).data == {
            "ok": True
        }
    assert auth.calls == 3
    assert len({r.headers["Authorization"] for r in requests}) == 3
    assert len(delays) == 2 and delays[1] == 2


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "DELETE"])
@pytest.mark.parametrize("failure", ["timeout", "503"])
async def test_no_implicit_retry(
    settings: ETradeSettings, auth: FakeAuthenticator, method: HttpMethod, failure: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout("fake-secret", request=request)
        return httpx.Response(503)

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as api:
        with pytest.raises((ETradeTransportError, ETradeApiError)) as exc:
            await api.request(method, "/v1/x")
    assert auth.calls == 1
    assert "fake-secret" not in "".join(traceback.format_exception(exc.value))


async def test_retry_exhaustion(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(lambda r: httpx.Response(503)),
        retry_policy=RetryPolicy(base_delay_seconds=0),
    ) as api:
        with pytest.raises(ETradeApiError):
            await api.request("GET", "/v1/x", safety=RetrySafety.SAFE_READ)
    assert auth.calls == 3


async def test_redirect_not_followed_on_injected_client(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(302, headers={"Location": "https://evil.example"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
        auth=("fake-other-user", "fake-other-password"),
    ) as client:
        async with ApiTransport(settings, authenticator=auth, http_client=client) as api:
            with pytest.raises(ETradeApiError):
                await api.request("GET", "/v1/x")
        assert not client.is_closed
    assert len(seen) == 1
    assert seen[0].headers["Authorization"].startswith("OAuth ")


async def test_requests_really_overlap(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    both_arrived = asyncio.Event()
    count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        if count == 2:
            both_arrived.set()
        await both_arrived.wait()
        return httpx.Response(200, json={"path": request.url.path})

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as api:
        async with asyncio.timeout(2):
            first, second = await asyncio.gather(
                api.request("GET", "/v1/first"), api.request("GET", "/v1/second")
            )
    assert first.data == {"path": "/v1/first"}
    assert second.data == {"path": "/v1/second"}


async def test_cancellation_during_retry(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    sleeping = asyncio.Event()

    async def sleep(delay: float) -> None:
        sleeping.set()
        await asyncio.Event().wait()

    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(lambda r: httpx.Response(503)),
        sleep=sleep,
    ) as api:
        task = asyncio.create_task(api.request("GET", "/v1/x", safety=RetrySafety.SAFE_READ))
        await asyncio.wait_for(sleeping.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert auth.calls == 1


async def test_no_secret_leakage(
    settings: ETradeSettings, auth: FakeAuthenticator, caplog: pytest.LogCaptureFixture
) -> None:
    values = [
        "fake-key",
        "fake-secret",
        "fake-token",
        "fake-token-secret",
        "fake-signature-1",
        "fake-verifier",
        "fake-account",
        "fake-query",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"Error": {"code": "42", "message": " ".join(values)}},
            headers={"X-Correlation-ID": "fake-token"},
        )

    caplog.set_level(logging.DEBUG)
    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as api:
        with pytest.raises(ETradeApiError) as exc:
            await api.request(
                "GET",
                "/v1/accounts/fake-account/balance.json",
                params={"q": "fake-query"},
                operation="accounts.balance",
            )
    assert exc.value.broker_message is not None
    diagnostics = repr(exc.value) + str(vars(exc.value))
    for value in values:
        assert value not in diagnostics
    # Automatic HTTPX URL logs must not leak SDK URLs even with DEBUG enabled.
    for value in values:
        assert value not in caplog.text
    records = [r for r in caplog.records if r.name.startswith("etrade_python")]
    assert len(records) == 1
    for value in values:
        assert value not in repr(vars(records[0]))
    assert records[0].__dict__["operation"] == "accounts.balance"
    assert records[0].__dict__["status_code"] == 400


async def test_bearer_hook_redacted(settings: ETradeSettings) -> None:
    class BearerAuth:
        async def authenticate(self, request: httpx.Request) -> None:
            request.headers["Authorization"] = "Bearer fake-bearer"

    async with ApiTransport(
        settings,
        authenticator=BearerAuth(),
        http_transport=httpx.MockTransport(
            lambda r: httpx.Response(400, json={"message": "fake-bearer"})
        ),
    ) as api:
        with pytest.raises(ETradeApiError) as exc:
            await api.request("GET", "/v1/x")
    assert exc.value.broker_message == "[REDACTED]"


async def test_other_http_error(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.DecodingError("fake-secret")

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as api:
        with pytest.raises(ETradeTransportError, match="HTTP exchange failed"):
            await api.request("GET", "/v1/x")
