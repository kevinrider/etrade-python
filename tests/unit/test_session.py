import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr

from etrade_python import (
    AuthenticationRequired,
    AuthorizationExpired,
    ETradeApiError,
    ETradeCredentials,
    ETradeHttpAuthenticationError,
    ETradeSettings,
)
from etrade_python.auth import MemoryCredentialStore, OAuthClient, SessionManager, TokenStatus


def make_credentials(*, acquired_at: datetime, last_used_at: datetime) -> ETradeCredentials:
    return ETradeCredentials(
        access_token=SecretStr("fake-access-token"),
        access_token_secret=SecretStr("fake-access-secret"),
        acquired_at=acquired_at,
        last_used_at=last_used_at,
    )


async def test_session_statuses(settings: ETradeSettings) -> None:
    now = datetime(2026, 9, 26, 18, 0, tzinfo=UTC)
    oauth = OAuthClient(settings, http_transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    manager = SessionManager(
        settings=settings,
        oauth_client=oauth,
        credential_store=MemoryCredentialStore(),
        clock=lambda: now,
    )

    assert manager.status(None) is TokenStatus.MISSING
    assert (
        manager.status(make_credentials(acquired_at=now, last_used_at=now - timedelta(minutes=30)))
        is TokenStatus.ACTIVE
    )
    assert (
        manager.status(make_credentials(acquired_at=now, last_used_at=now - timedelta(hours=2)))
        is TokenStatus.INACTIVE_RENEWABLE
    )
    assert (
        manager.status(
            make_credentials(
                acquired_at=datetime(2026, 9, 26, 2, 0, tzinfo=UTC),
                last_used_at=datetime(2026, 9, 26, 3, 0, tzinfo=UTC),
            ),
            now=datetime(2026, 9, 27, 5, 0, tzinfo=UTC),
        )
        is TokenStatus.EXPIRED
    )


async def test_missing_credentials_raise_authentication_required(settings: ETradeSettings) -> None:
    oauth = OAuthClient(settings, http_transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    manager = SessionManager(
        settings=settings, oauth_client=oauth, credential_store=MemoryCredentialStore()
    )

    with pytest.raises(AuthenticationRequired):
        await manager.ensure_active()


async def test_active_credentials_update_last_used(settings: ETradeSettings) -> None:
    now = datetime(2026, 9, 26, 18, 0, tzinfo=UTC)
    store = MemoryCredentialStore()
    await store.save(
        "default",
        make_credentials(
            acquired_at=now - timedelta(hours=1),
            last_used_at=now - timedelta(minutes=1),
        ),
    )
    oauth = OAuthClient(settings, http_transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    manager = SessionManager(
        settings=settings, oauth_client=oauth, credential_store=store, clock=lambda: now
    )

    credentials = await manager.ensure_active()

    assert credentials.last_used_at == now
    assert (await store.load("default")) == credentials


async def test_inactive_credentials_renew_once_under_concurrency(settings: ETradeSettings) -> None:
    now = datetime(2026, 9, 26, 18, 0, tzinfo=UTC)
    store = MemoryCredentialStore()
    await store.save(
        "default",
        make_credentials(
            acquired_at=now - timedelta(hours=1),
            last_used_at=now - timedelta(hours=2),
        ),
    )
    renew_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal renew_calls
        renew_calls += 1
        return httpx.Response(200, text="Access Token has been renewed")

    oauth = OAuthClient(settings, http_transport=httpx.MockTransport(handler))
    manager = SessionManager(
        settings=settings, oauth_client=oauth, credential_store=store, clock=lambda: now
    )

    results = await asyncio.gather(*(manager.ensure_active() for _ in range(5)))

    assert renew_calls == 1
    assert all(result.renewed_at == now for result in results)
    assert (await store.load("default")) is not None


async def test_expired_credentials_raise_authorization_expired(settings: ETradeSettings) -> None:
    now = datetime(2026, 9, 27, 5, 0, tzinfo=UTC)
    store = MemoryCredentialStore()
    await store.save(
        "default",
        make_credentials(
            acquired_at=datetime(2026, 9, 26, 2, 0, tzinfo=UTC),
            last_used_at=datetime(2026, 9, 26, 3, 0, tzinfo=UTC),
        ),
    )
    oauth = OAuthClient(settings, http_transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    manager = SessionManager(
        settings=settings, oauth_client=oauth, credential_store=store, clock=lambda: now
    )

    with pytest.raises(AuthorizationExpired):
        await manager.ensure_active()


async def test_renewal_failure_is_structured(settings: ETradeSettings) -> None:
    now = datetime(2026, 9, 26, 18, 0, tzinfo=UTC)
    store = MemoryCredentialStore()
    await store.save(
        "default",
        make_credentials(
            acquired_at=now - timedelta(hours=1),
            last_used_at=now - timedelta(hours=2),
        ),
    )
    oauth = OAuthClient(
        settings,
        http_transport=httpx.MockTransport(
            lambda r: httpx.Response(401, json={"message": "denied"})
        ),
    )
    manager = SessionManager(
        settings=settings, oauth_client=oauth, credential_store=store, clock=lambda: now
    )

    with pytest.raises(ETradeHttpAuthenticationError):
        await manager.ensure_active()


async def test_renewal_redirect_preserves_credentials(settings: ETradeSettings) -> None:
    now = datetime(2026, 9, 26, 18, 0, tzinfo=UTC)
    credentials = make_credentials(
        acquired_at=now - timedelta(hours=3), last_used_at=now - timedelta(hours=2)
    )
    store = MemoryCredentialStore()
    await store.save("default", credentials)
    async with OAuthClient(
        settings,
        http_transport=httpx.MockTransport(
            lambda request: httpx.Response(302, headers={"Location": "https://example.invalid/"})
        ),
    ) as oauth:
        manager = SessionManager(
            settings=settings, oauth_client=oauth, credential_store=store, clock=lambda: now
        )
        with pytest.raises(ETradeApiError) as exc:
            await manager.ensure_active()

    assert exc.value.status_code == 302
    assert await store.load("default") == credentials
