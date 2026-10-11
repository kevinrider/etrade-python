from datetime import UTC, datetime

import httpx
import keyring
import pytest
from pydantic import SecretStr

from etrade_python import (
    AuthenticationRequired,
    ETradeClient,
    ETradeCredentials,
    ETradeSettings,
    ETradeTransportError,
    ETradeValidationError,
)
from etrade_python.auth.stores import CredentialStore, KeyringCredentialStore, MemoryCredentialStore
from etrade_python.transport import ApiTransport


class TrackingTransport(httpx.AsyncBaseTransport):
    closed = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError("Construction must not make requests")

    async def aclose(self) -> None:
        self.closed = True


async def test_owned_lifecycle(settings: ETradeSettings) -> None:
    transport = TrackingTransport()
    client = ETradeClient(settings, http_transport=transport)
    assert not transport.closed
    async with client as entered:
        assert entered is client
    assert transport.closed
    await client.aclose()
    with pytest.raises(ETradeTransportError, match="closed"):
        await client.__aenter__()


async def test_borrowed_lifecycle(settings: ETradeSettings) -> None:
    async with httpx.AsyncClient(transport=TrackingTransport()) as http_client:
        async with ETradeClient(settings, http_client=http_client):
            pass
        assert not http_client.is_closed
    assert http_client.is_closed


async def test_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETRADE_CONSUMER_KEY", "fake-key")
    monkeypatch.setenv("ETRADE_CONSUMER_SECRET", "fake-secret")
    async with ETradeClient.from_environment():
        pass


def test_mutually_exclusive_injection(settings: ETradeSettings) -> None:
    client = httpx.AsyncClient()
    with pytest.raises(ETradeValidationError, match="not both"):
        ApiTransport(settings, http_client=client, http_transport=TrackingTransport())


@pytest.fixture(params=["memory", "keyring"])
def shared_store(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> CredentialStore:
    if request.param == "memory":
        return MemoryCredentialStore()
    entries: dict[tuple[str, str], str] = {}

    def get_password(service: str, profile: str) -> str | None:
        return entries.get((service, profile))

    def set_password(service: str, profile: str, value: str) -> None:
        entries[(service, profile)] = value

    def delete_password(service: str, profile: str) -> None:
        entries.pop((service, profile), None)

    monkeypatch.setattr(keyring, "get_password", get_password)
    monkeypatch.setattr(keyring, "set_password", set_password)
    monkeypatch.setattr(keyring, "delete_password", delete_password)
    return KeyringCredentialStore()


def namespace_credentials(token: str) -> ETradeCredentials:
    now = datetime(2026, 9, 26, 18, tzinfo=UTC)
    return ETradeCredentials(
        access_token=SecretStr(token),
        access_token_secret=SecretStr("fake-token-secret"),
        acquired_at=now,
        last_used_at=now,
    )


@pytest.mark.parametrize(
    ("environment", "consumer_key", "profile"),
    [
        ("production", "fake-key", "default"),
        ("sandbox", "different-key", "default"),
        ("sandbox", "fake-key", "personal"),
        ("sandbox", "fake-key", "personal:账户"),
    ],
)
async def test_clients_isolate_credential_namespaces(
    settings: ETradeSettings,
    shared_store: CredentialStore,
    environment: str,
    consumer_key: str,
    profile: str,
) -> None:
    other_settings = ETradeSettings(
        consumer_key=consumer_key, consumer_secret="other-secret", environment=environment
    )
    original = namespace_credentials("fake-original-token")
    other = namespace_credentials("fake-other-token")
    async with (
        ETradeClient(settings, credential_store=shared_store) as first,
        ETradeClient(other_settings, credential_store=shared_store, profile=profile) as second,
    ):
        await first.session.save(original)
        assert await second.session.load() is None
        await second.session.save(other)
        assert await first.session.load() == original
        assert await second.session.load() == other
        await first.session.delete()
        assert await first.session.load() is None
        assert await second.session.load() == other


async def test_clients_share_identical_credential_namespace(
    settings: ETradeSettings, shared_store: CredentialStore
) -> None:
    credentials = namespace_credentials("fake-shared-token")
    async with (
        ETradeClient(settings, credential_store=shared_store) as first,
        ETradeClient(settings, credential_store=shared_store) as second,
    ):
        await first.session.save(credentials)
        assert await second.session.load() == credentials
        await second.session.delete()
        assert await first.session.load() is None


async def test_legacy_credentials_are_ignored_and_preserved(
    settings: ETradeSettings, shared_store: CredentialStore
) -> None:
    legacy = namespace_credentials("fake-legacy-token")
    await shared_store.save("default", legacy)
    async with ETradeClient(settings, credential_store=shared_store) as client:
        assert await client.session.load() is None
        with pytest.raises(AuthenticationRequired):
            await client.session.ensure_active()
        await client.session.save(namespace_credentials("fake-new-token"))
        assert await shared_store.load("default") == legacy
        await client.session.delete()
    assert await shared_store.load("default") == legacy
