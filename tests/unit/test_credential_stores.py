from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from etrade_python import ETradeCredentials, ETradeValidationError
from etrade_python.auth.stores import KeyringCredentialStore, MemoryCredentialStore


def credentials() -> ETradeCredentials:
    return ETradeCredentials(
        access_token=SecretStr("fake-access-token"),
        access_token_secret=SecretStr("fake-access-secret"),
        acquired_at=datetime(2026, 1, 1, tzinfo=UTC),
        last_used_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def test_memory_store_round_trip() -> None:
    store = MemoryCredentialStore()
    assert await store.load("default") is None

    original = credentials()
    await store.save("default", original)
    assert await store.load("default") == original

    await store.delete("default")
    assert await store.load("default") is None


async def test_keyring_store_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    saved: dict[tuple[str, str], str] = {}

    def get_password(service_name: str, username: str) -> str | None:
        return saved.get((service_name, username))

    def set_password(service_name: str, username: str, password: str) -> None:
        saved[(service_name, username)] = password

    def delete_password(service_name: str, username: str) -> None:
        saved.pop((service_name, username))

    monkeypatch.setattr("keyring.get_password", get_password)
    monkeypatch.setattr("keyring.set_password", set_password)
    monkeypatch.setattr("keyring.delete_password", delete_password)

    store = KeyringCredentialStore(service_name="fake-service")
    original = credentials()
    await store.save("profile", original)

    raw = saved[("fake-service", "profile")]
    assert "fake-access-token" in raw
    assert await store.load("profile") == original

    await store.delete("profile")
    assert await store.load("profile") is None


async def test_keyring_store_invalid_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    def invalid_payload(service: str, profile: str) -> str:
        return '{"bad": true}'

    monkeypatch.setattr("keyring.get_password", invalid_payload)
    store = KeyringCredentialStore()

    with pytest.raises(ETradeValidationError, match="Stored"):
        await store.load("profile")
