import logging
import re
import traceback
from datetime import UTC, datetime
from urllib.parse import unquote

import httpx
import pytest
from pydantic import SecretStr

from etrade_python import (
    ETradeApiError,
    ETradeCredentials,
    ETradeResponseError,
    ETradeSettings,
    RequestToken,
)
from etrade_python.auth.oauth import OAuthClient


def test_oauth_signature_matches_official_example() -> None:
    settings = ETradeSettings(
        consumer_key="c5bb4dcb7bd6826c7c4340df3f791188",
        consumer_secret="7d30246211192cda43ede3abd9b393b9",
        environment="production",
    )
    credentials = ETradeCredentials(
        access_token=SecretStr("VbiNYl63EejjlKdQM6FeENzcnrLACrZ2JYD6NQROfVI="),
        access_token_secret=SecretStr("XCF9RzyQr4UEPloA+WlC06BnTfYC1P0Fwr3GUw/B0Es="),
        acquired_at=datetime(2026, 1, 1, tzinfo=UTC),
        last_used_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    oauth = OAuthClient(
        settings,
        nonce_factory=lambda: "0bba225a40d1bbac2430aa0c6163ce44",
        timestamp_factory=lambda: 1344885636,
    )
    request = httpx.Request("GET", "https://api.etrade.com/v1/accounts/list")

    oauth.sign_request(request, credentials)

    header = request.headers["Authorization"]
    assert 'oauth_signature="UOnPVdzExTAgHkcGWLLfeTaaMSM%3D"' in header
    assert "oauth_token=" in header
    assert "oauth_token_secret" not in header


def test_authorization_url() -> None:
    settings = ETradeSettings(consumer_key="fake key", consumer_secret="fake-secret")
    token = RequestToken(
        oauth_token=SecretStr("fake/token="),
        oauth_token_secret=SecretStr("fake-token-secret"),
    )
    oauth = OAuthClient(settings)

    authorization = oauth.get_authorization_url(token)

    assert authorization.request_token is token
    assert authorization.url.startswith("https://us.etrade.com/e/t/etws/authorize?")
    assert "key=fake+key" in authorization.url
    assert "token=fake%2Ftoken%3D" in authorization.url
    assert authorization.model_dump()["url"] == authorization.url
    for representation in (repr(authorization), str(authorization)):
        for sensitive_value in (
            authorization.url,
            "fake/token=",
            "fake%2Ftoken%3D",
            "fake-token-secret",
        ):
            assert sensitive_value not in representation


async def test_request_token_exchange_contract(settings: ETradeSettings) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.method == "GET"
        assert request.url == "https://api.etrade.com/oauth/request_token"
        assert 'oauth_callback="oob"' in request.headers["Authorization"]
        return httpx.Response(
            200,
            content=(
                b"oauth_token=fake-request-token&"
                b"oauth_token_secret=fake-request-secret&"
                b"oauth_callback_confirmed=true"
            ),
        )

    async with OAuthClient(settings, http_transport=httpx.MockTransport(handler)) as oauth:
        token = await oauth.get_request_token()

    assert len(seen) == 1
    assert token.oauth_token.get_secret_value() == "fake-request-token"
    assert token.oauth_token_secret.get_secret_value() == "fake-request-secret"
    assert token.oauth_callback_confirmed is True


async def test_access_token_exchange_includes_verifier(settings: ETradeSettings) -> None:
    request_token = RequestToken(
        oauth_token=SecretStr("fake-request-token"),
        oauth_token_secret=SecretStr("fake-request-secret"),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        header = unquote(request.headers["Authorization"])
        assert 'oauth_token="fake-request-token"' in header
        assert 'oauth_verifier="fake-verifier"' in header
        return httpx.Response(
            200,
            content=b"oauth_token=fake-access-token&oauth_token_secret=fake-access-secret",
        )

    async with OAuthClient(settings, http_transport=httpx.MockTransport(handler)) as oauth:
        credentials = await oauth.exchange_verifier(request_token, "fake-verifier")

    assert credentials.access_token.get_secret_value() == "fake-access-token"
    assert credentials.access_token_secret.get_secret_value() == "fake-access-secret"


@pytest.mark.parametrize(
    ("method_name", "path", "expected"),
    [
        ("renew_access_token", "/oauth/renew_access_token", "Access Token has been renewed"),
        ("revoke_access_token", "/oauth/revoke_access_token", "Revoked Access Token"),
    ],
)
@pytest.mark.parametrize("status_code", [200, 204, 299])
async def test_renew_and_revoke_contract(
    settings: ETradeSettings, method_name: str, path: str, expected: str, status_code: int
) -> None:
    credentials = ETradeCredentials(
        access_token=SecretStr("fake-access-token"),
        access_token_secret=SecretStr("secret"),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == path
        assert 'oauth_token="fake-access-token"' in unquote(request.headers["Authorization"])
        return httpx.Response(status_code, text=expected)

    async with OAuthClient(settings, http_transport=httpx.MockTransport(handler)) as oauth:
        if method_name == "renew_access_token":
            result = await oauth.renew_access_token(credentials)
        else:
            result = await oauth.revoke_access_token(credentials)

    assert result.message == expected


@pytest.mark.parametrize("operation", ["request", "exchange", "renew", "revoke"])
@pytest.mark.parametrize("status_code", [199, 300, 301, 302, 303, 307, 308, 400, 401, 500])
async def test_oauth_rejects_non_success_statuses(
    settings: ETradeSettings, operation: str, status_code: int
) -> None:
    credentials = ETradeCredentials(
        access_token=SecretStr("fake-access-token"),
        access_token_secret=SecretStr("fake-access-secret"),
    )
    request_token = RequestToken(
        oauth_token=SecretStr("fake-request-token"),
        oauth_token_secret=SecretStr("fake-request-secret"),
    )
    seen: list[httpx.Request] = []
    responses: list[httpx.Response] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        response = httpx.Response(
            status_code,
            headers={"Location": "https://example.invalid/redirect", "X-Correlation-ID": "fake-id"},
            content=b"oauth_token=fake-token&oauth_token_secret=fake-secret",
        )
        responses.append(response)
        return response

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    ) as client:
        async with OAuthClient(settings, http_client=client) as oauth:
            with pytest.raises(ETradeApiError) as exc:
                if operation == "request":
                    await oauth.get_request_token()
                elif operation == "exchange":
                    await oauth.exchange_verifier(request_token, "fake-verifier")
                elif operation == "renew":
                    await oauth.renew_access_token(credentials)
                else:
                    await oauth.revoke_access_token(credentials)
        assert not client.is_closed

    assert exc.value.status_code == status_code
    assert exc.value.request_id == "fake-id"
    assert len(seen) == 1
    assert responses[0].is_closed


async def test_invalid_oauth_form_response(settings: ETradeSettings) -> None:
    async with OAuthClient(
        settings, http_transport=httpx.MockTransport(lambda r: httpx.Response(200, text=""))
    ) as oauth:
        with pytest.raises(ETradeResponseError):
            await oauth.get_request_token()


@pytest.mark.parametrize("operation", ["request", "exchange", "renew", "revoke"])
@pytest.mark.parametrize("decoded", [False, True])
async def test_oauth_error_redacts_individual_header_secrets(
    settings: ETradeSettings,
    caplog: pytest.LogCaptureFixture,
    operation: str,
    decoded: bool,
) -> None:
    credentials = ETradeCredentials(
        access_token=SecretStr("sensitiveAccessToken/+="),
        access_token_secret=SecretStr("fake-access-secret"),
    )
    request_token = RequestToken(
        oauth_token=SecretStr("sensitiveRequestToken/+="),
        oauth_token_secret=SecretStr("fake-request-secret"),
    )
    verifier = "sensitiveVerifier/+="
    echoed_values: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        parameters = dict(
            re.findall(r'(oauth_\w+)="([^"\r\n]*)"', request.headers["Authorization"])
        )
        for name in ("oauth_consumer_key", "oauth_token", "oauth_verifier", "oauth_signature"):
            if name in parameters:
                value = parameters[name]
                echoed_values.append(unquote(value) if decoded else value)
        # No field labels: redaction must recognize the individual secret values.
        return httpx.Response(
            400,
            json={"Error": {"code": "42", "message": "Rejected " + " ".join(echoed_values)}},
            headers={"X-Correlation-ID": echoed_values[-1]},
        )

    caplog.set_level(logging.DEBUG)
    async with OAuthClient(settings, http_transport=httpx.MockTransport(handler)) as oauth:
        with pytest.raises(ETradeApiError) as exc:
            if operation == "request":
                await oauth.get_request_token()
            elif operation == "exchange":
                await oauth.exchange_verifier(request_token, verifier)
            elif operation == "renew":
                await oauth.renew_access_token(credentials)
            else:
                await oauth.revoke_access_token(credentials)

    assert exc.value.status_code == 400
    assert exc.value.broker_code == "42"
    assert exc.value.broker_message is not None
    assert "Rejected" in exc.value.broker_message
    assert "[REDACTED]" in exc.value.broker_message
    diagnostics = (
        str(exc.value)
        + repr(exc.value)
        + repr(vars(exc.value))
        + "".join(traceback.format_exception(exc.value))
        + caplog.text
        + repr([vars(record) for record in caplog.records])
    )
    for value in echoed_values:
        assert value not in diagnostics


def test_oauth_models_do_not_repr_secrets() -> None:
    credentials = ETradeCredentials(
        access_token=SecretStr("fake-access-token"),
        access_token_secret=SecretStr("secret"),
    )
    assert "fake-access-token" not in repr(credentials)
    assert "secret" not in repr(credentials)
