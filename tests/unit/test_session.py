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
    ETradeError,
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


@pytest.mark.parametrize("inactive_minutes", [1, 120])
async def test_explicit_renewal_contacts_broker(
    settings: ETradeSettings, inactive_minutes: int
) -> None:
    now = datetime(2026, 9, 26, 18, tzinfo=UTC)
    completed_at = now + timedelta(seconds=5)
    credentials = make_credentials(
        acquired_at=now - timedelta(hours=3),
        last_used_at=now - timedelta(minutes=inactive_minutes),
    )
    clock = now
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal clock
        seen.append(request)
        clock = completed_at
        return httpx.Response(200, text="Access Token has been renewed")

    async with OAuthClient(settings, http_transport=httpx.MockTransport(handler)) as oauth:
        manager = SessionManager(
            settings=settings,
            oauth_client=oauth,
            credential_store=MemoryCredentialStore(),
            clock=lambda: clock,
        )
        await manager.save(credentials)
        renewed = await manager.renew()
        assert await manager.load() == renewed

    assert len(seen) == 1
    assert seen[0].url.path == "/oauth/renew_access_token"
    assert renewed.acquired_at == credentials.acquired_at
    assert renewed.access_token == credentials.access_token
    assert renewed.access_token_secret == credentials.access_token_secret
    assert renewed.last_used_at == completed_at
    assert renewed.renewed_at == completed_at


@pytest.mark.parametrize("expired", [False, True])
async def test_explicit_renewal_rejects_missing_or_expired_credentials(
    settings: ETradeSettings, expired: bool
) -> None:
    now = datetime(2026, 9, 27, 18, tzinfo=UTC)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Missing or expired credentials must not reach the broker")

    async with OAuthClient(settings, http_transport=httpx.MockTransport(handler)) as oauth:
        manager = SessionManager(
            settings=settings,
            oauth_client=oauth,
            credential_store=MemoryCredentialStore(),
            clock=lambda: now,
        )
        credentials = None
        if expired:
            credentials = make_credentials(
                acquired_at=now - timedelta(days=1), last_used_at=now - timedelta(days=1)
            )
            await manager.save(credentials)
        with pytest.raises(AuthorizationExpired if expired else AuthenticationRequired):
            await manager.renew()
        assert await manager.load() == credentials


@pytest.mark.parametrize("failure", ["redirect", "denied", "server", "network", "cancelled"])
async def test_explicit_renewal_failure_preserves_credentials(
    settings: ETradeSettings, failure: str
) -> None:
    now = datetime(2026, 9, 26, 18, tzinfo=UTC)
    credentials = make_credentials(
        acquired_at=now - timedelta(hours=1), last_used_at=now - timedelta(minutes=1)
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "network":
            raise httpx.ConnectError("Fake connection failure", request=request)
        if failure == "cancelled":
            raise asyncio.CancelledError
        return httpx.Response({"redirect": 302, "denied": 401, "server": 500}[failure])

    async with OAuthClient(settings, http_transport=httpx.MockTransport(handler)) as oauth:
        manager = SessionManager(
            settings=settings,
            oauth_client=oauth,
            credential_store=MemoryCredentialStore(),
            clock=lambda: now,
        )
        await manager.save(credentials)
        with pytest.raises(asyncio.CancelledError if failure == "cancelled" else ETradeError):
            await manager.renew()
        assert await manager.load() == credentials


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

    oauth = OAuthClient(settings, http_transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    manager = SessionManager(
        settings=settings, oauth_client=oauth, credential_store=store, clock=lambda: now
    )
    await manager.save(
        make_credentials(
            acquired_at=now - timedelta(hours=1),
            last_used_at=now - timedelta(minutes=1),
        ),
    )

    credentials = await manager.ensure_active()

    assert credentials.last_used_at == now
    assert (await manager.load()) == credentials


async def test_inactive_credentials_renew_once_under_concurrency(settings: ETradeSettings) -> None:
    now = datetime(2026, 9, 26, 18, 0, tzinfo=UTC)
    store = MemoryCredentialStore()

    renew_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal renew_calls
        renew_calls += 1
        return httpx.Response(200, text="Access Token has been renewed")

    oauth = OAuthClient(settings, http_transport=httpx.MockTransport(handler))
    manager = SessionManager(
        settings=settings, oauth_client=oauth, credential_store=store, clock=lambda: now
    )
    await manager.save(
        make_credentials(
            acquired_at=now - timedelta(hours=1),
            last_used_at=now - timedelta(hours=2),
        ),
    )

    results = await asyncio.gather(*(manager.ensure_active() for _ in range(5)))

    assert renew_calls == 1
    assert all(result.renewed_at == now for result in results)
    assert (await manager.load()) is not None


async def test_expired_credentials_raise_authorization_expired(settings: ETradeSettings) -> None:
    now = datetime(2026, 9, 27, 5, 0, tzinfo=UTC)
    store = MemoryCredentialStore()

    oauth = OAuthClient(settings, http_transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    manager = SessionManager(
        settings=settings, oauth_client=oauth, credential_store=store, clock=lambda: now
    )
    await manager.save(
        make_credentials(
            acquired_at=datetime(2026, 9, 26, 2, 0, tzinfo=UTC),
            last_used_at=datetime(2026, 9, 26, 3, 0, tzinfo=UTC),
        ),
    )

    with pytest.raises(AuthorizationExpired):
        await manager.ensure_active()


async def test_renewal_failure_is_structured(settings: ETradeSettings) -> None:
    now = datetime(2026, 9, 26, 18, 0, tzinfo=UTC)
    store = MemoryCredentialStore()

    oauth = OAuthClient(
        settings,
        http_transport=httpx.MockTransport(
            lambda r: httpx.Response(401, json={"message": "denied"})
        ),
    )
    manager = SessionManager(
        settings=settings, oauth_client=oauth, credential_store=store, clock=lambda: now
    )
    await manager.save(
        make_credentials(
            acquired_at=now - timedelta(hours=1),
            last_used_at=now - timedelta(hours=2),
        ),
    )

    with pytest.raises(ETradeHttpAuthenticationError):
        await manager.ensure_active()


async def test_renewal_redirect_preserves_credentials(settings: ETradeSettings) -> None:
    now = datetime(2026, 9, 26, 18, 0, tzinfo=UTC)
    credentials = make_credentials(
        acquired_at=now - timedelta(hours=3), last_used_at=now - timedelta(hours=2)
    )
    store = MemoryCredentialStore()
    async with OAuthClient(
        settings,
        http_transport=httpx.MockTransport(
            lambda request: httpx.Response(302, headers={"Location": "https://example.invalid/"})
        ),
    ) as oauth:
        manager = SessionManager(
            settings=settings, oauth_client=oauth, credential_store=store, clock=lambda: now
        )
        await manager.save(credentials)
        with pytest.raises(ETradeApiError) as exc:
            await manager.ensure_active()

    assert exc.value.status_code == 302
    assert await manager.load() == credentials


@pytest.mark.parametrize(
    ("environment", "consumer_key", "profile"),
    [
        ("production", "fake-key", "default"),
        ("sandbox", "other-key", "default"),
        ("sandbox", "fake-key", "personal"),
    ],
)
async def test_renewal_preserves_other_namespaces(
    settings: ETradeSettings, environment: str, consumer_key: str, profile: str
) -> None:
    now = datetime(2026, 9, 26, 18, tzinfo=UTC)
    credentials = make_credentials(
        acquired_at=now - timedelta(hours=3), last_used_at=now - timedelta(hours=2)
    )
    other_settings = ETradeSettings(
        consumer_key=consumer_key, consumer_secret="other-secret", environment=environment
    )
    store = MemoryCredentialStore()
    async with OAuthClient(
        settings, http_transport=httpx.MockTransport(lambda r: httpx.Response(200, text="Renewed"))
    ) as oauth:
        manager = SessionManager(
            settings=settings, oauth_client=oauth, credential_store=store, clock=lambda: now
        )
        other = SessionManager(
            settings=other_settings,
            oauth_client=oauth,
            credential_store=store,
            clock=lambda: now,
            profile=profile,
        )
        await manager.save(credentials)
        await other.save(credentials)
        renewed = await manager.ensure_active()

        assert renewed.renewed_at == now
        assert await manager.load() == renewed
        assert await other.load() == credentials


async def test_custom_store_receives_namespaced_keys(
    settings: ETradeSettings, caplog: pytest.LogCaptureFixture
) -> None:
    class RecordingStore(MemoryCredentialStore):
        def __init__(self) -> None:
            super().__init__()
            self.keys: list[str] = []

        async def load(self, profile: str) -> ETradeCredentials | None:
            self.keys.append(profile)
            return await super().load(profile)

        async def save(self, profile: str, credentials: ETradeCredentials) -> None:
            self.keys.append(profile)
            await super().save(profile, credentials)

        async def delete(self, profile: str) -> None:
            self.keys.append(profile)
            await super().delete(profile)

    store = RecordingStore()
    now = datetime(2026, 9, 26, 18, tzinfo=UTC)
    credentials = make_credentials(acquired_at=now, last_used_at=now)
    async with OAuthClient(settings) as oauth:
        manager = SessionManager(settings=settings, oauth_client=oauth, credential_store=store)
        await manager.save(credentials)
        assert await manager.load() == credentials
        await manager.delete()

    assert len(store.keys) == 3
    assert len(set(store.keys)) == 1
    environment, fingerprint, profile = store.keys[0].split(":")
    assert environment == "sandbox"
    assert profile == "default"
    assert len(fingerprint) == 64
    assert all(character in "0123456789abcdef" for character in fingerprint)
    for secret in (
        settings.consumer_key,
        settings.consumer_secret,
        credentials.access_token,
        credentials.access_token_secret,
    ):
        assert secret.get_secret_value() not in store.keys[0]
    assert store.keys[0] not in caplog.text
