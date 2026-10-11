import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr

from etrade_python import ETradeCredentials, ETradeError, ETradeSettings
from etrade_python.auth import MemoryCredentialStore, OAuthClient, SessionManager
from etrade_python.auth.session import SessionAuthenticator
from etrade_python.transport import ApiTransport
from etrade_python.transport.retry import RetryPolicy, RetrySafety


@pytest.mark.parametrize(
    "outcome", ["200", "204", "bad-json", "302", "400", "401", "503", "timeout", "cancel", "retry"]
)
async def test_usage_follows_confirmed_http_exchange(
    settings: ETradeSettings, outcome: str
) -> None:
    now = datetime(2026, 9, 26, 18, tzinfo=UTC)
    credentials = ETradeCredentials(
        access_token=SecretStr("fake-token"),
        access_token_secret=SecretStr("fake-token-secret"),
        acquired_at=now - timedelta(hours=1),
        last_used_at=now - timedelta(minutes=5),
    )
    clock = now
    calls = 0
    store = MemoryCredentialStore()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal clock, calls
        # Signing and unsuccessful attempts must not record usage.
        assert await manager.load() == credentials
        calls += 1
        clock = now + timedelta(minutes=calls)
        if outcome == "timeout":
            raise httpx.ReadTimeout("Fake timeout", request=request)
        if outcome == "cancel":
            raise asyncio.CancelledError
        if outcome == "retry":
            return httpx.Response(503 if calls == 1 else 200, json={"ok": True})
        if outcome == "bad-json":
            return httpx.Response(
                200, content=b"invalid", headers={"Content-Type": "application/json"}
            )
        return httpx.Response(int(outcome), json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        async with OAuthClient(settings, http_client=http_client) as oauth:
            manager = SessionManager(
                settings=settings, oauth_client=oauth, credential_store=store, clock=lambda: clock
            )
            await manager.save(credentials)
            async with ApiTransport(
                settings,
                authenticator=SessionAuthenticator(manager, oauth),
                http_client=http_client,
                retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0),
            ) as transport:
                safety = RetrySafety.SAFE_READ if outcome == "retry" else RetrySafety.NEVER
                if outcome in {"200", "204", "retry"}:
                    await transport.request("GET", "/v1/example.json", safety=safety)
                else:
                    with pytest.raises(
                        asyncio.CancelledError if outcome == "cancel" else ETradeError
                    ):
                        await transport.request("GET", "/v1/example.json", safety=safety)

            stored = await manager.load()
            assert stored is not None
            if outcome in {"200", "204", "bad-json", "retry"}:
                assert stored.last_used_at == clock
                assert stored.acquired_at == credentials.acquired_at
                assert stored.renewed_at is None
            else:
                assert stored == credentials
            assert calls == (2 if outcome == "retry" else 1)


async def test_usage_storage_failure_preserves_successful_response(
    settings: ETradeSettings, caplog: pytest.LogCaptureFixture
) -> None:
    now = datetime(2026, 9, 26, 18, tzinfo=UTC)
    calls = 0
    fail_save = False

    class FailingStore(MemoryCredentialStore):
        async def save(self, profile: str, credentials: ETradeCredentials) -> None:
            if fail_save:
                raise ValueError("fake-token-secret")
            await super().save(profile, credentials)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal fail_save, calls
        calls += 1
        fail_save = True
        return httpx.Response(200, json={"confirmed": True})

    credentials = ETradeCredentials(
        access_token=SecretStr("fake-token"),
        access_token_secret=SecretStr("fake-token-secret"),
        acquired_at=now - timedelta(hours=1),
        last_used_at=now - timedelta(minutes=5),
    )
    caplog.set_level(logging.WARNING)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        async with OAuthClient(settings, http_client=http_client) as oauth:
            manager = SessionManager(
                settings=settings,
                oauth_client=oauth,
                credential_store=FailingStore(),
                clock=lambda: now,
            )
            await manager.save(credentials)
            async with ApiTransport(
                settings,
                authenticator=SessionAuthenticator(manager, oauth),
                http_client=http_client,
            ) as transport:
                response = await transport.request("POST", "/v1/example.json")

    assert response.data == {"confirmed": True}
    assert calls == 1
    assert "Could not record authenticated request usage" in caplog.text
    assert "fake-token" not in caplog.text
