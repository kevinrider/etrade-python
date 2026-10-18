"""OAuth access-token lifecycle management."""

import asyncio
import hashlib
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

import httpx

from etrade_python.auth.credentials import ETradeCredentials
from etrade_python.auth.oauth import OAuthClient
from etrade_python.auth.stores.base import CoordinatedCredentialStore, CredentialStore
from etrade_python.config import ETradeSettings
from etrade_python.exceptions import AuthenticationRequired, AuthorizationExpired

EASTERN = ZoneInfo("America/New_York")
INACTIVITY_SECONDS = 7200


class TokenStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE_RENEWABLE = "inactive_renewable"
    EXPIRED = "expired"
    MISSING = "missing"


class SessionManager:
    """Decide whether persisted credentials are usable, renewable, or expired."""

    def __init__(
        self,
        *,
        settings: ETradeSettings,
        oauth_client: OAuthClient,
        credential_store: CredentialStore,
        profile: str = "default",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._oauth_client = oauth_client
        self._credential_store = credential_store
        consumer_fingerprint = hashlib.sha256(
            settings.consumer_key.get_secret_value().encode("utf-8")
        ).hexdigest()
        self._storage_key = f"{settings.environment.value}:{consumer_fingerprint}:{profile}"
        self._clock = clock or (lambda: datetime.now(UTC))
        self._renewal_lock = asyncio.Lock()

    @asynccontextmanager
    async def _transaction(self) -> AsyncGenerator[None]:
        async with self._renewal_lock:
            if isinstance(self._credential_store, CoordinatedCredentialStore):
                async with self._credential_store.lock(self._storage_key):
                    yield
            else:
                # Preserve the original contract for existing custom stores.
                yield

    async def _load(self) -> ETradeCredentials | None:
        return await self._credential_store.load(self._storage_key)

    async def ensure_active(self) -> ETradeCredentials:
        async with self._transaction():
            now = self._now()
            credentials = await self._load()
            status = self.status(credentials, now=now)
            if status is TokenStatus.MISSING:
                raise AuthenticationRequired("E*TRADE authorization is required")
            if credentials is None:
                raise AuthenticationRequired("E*TRADE authorization is required")
            if status is TokenStatus.EXPIRED:
                raise AuthorizationExpired("E*TRADE authorization has expired")
            if status is TokenStatus.ACTIVE:
                return credentials
            return await self._renew(credentials)

    async def renew(self) -> ETradeCredentials:
        """Renew same-day credentials with the broker, even when locally active."""
        async with self._transaction():
            credentials = await self._load()
            if credentials is None:
                raise AuthenticationRequired("E*TRADE authorization is required")
            if self.status(credentials) is TokenStatus.EXPIRED:
                raise AuthorizationExpired("E*TRADE authorization has expired")
            return await self._renew(credentials)

    async def _renew(self, credentials: ETradeCredentials) -> ETradeCredentials:
        """Perform renewal while the caller holds the renewal lock."""
        result = await self._oauth_client.renew_access_token(credentials)
        renewed = result.credentials.with_renewal(max(self._now(), credentials.last_used_at))
        if credentials.renewed_at is not None and (
            renewed.renewed_at is None or credentials.renewed_at > renewed.renewed_at
        ):
            renewed = renewed.model_copy(update={"renewed_at": credentials.renewed_at})
        await self._save(renewed)
        return renewed

    async def save(self, credentials: ETradeCredentials) -> None:
        async with self._transaction():
            current = await self._load()
            if current is not None and _same_credentials(current, credentials):
                renewed = [t for t in (current.renewed_at, credentials.renewed_at) if t is not None]
                credentials = credentials.model_copy(
                    update={
                        "last_used_at": max(current.last_used_at, credentials.last_used_at),
                        "renewed_at": max(renewed) if renewed else None,
                    }
                )
            await self._save(credentials)

    async def _save(self, credentials: ETradeCredentials) -> None:
        await self._credential_store.save(self._storage_key, credentials)

    async def load(self) -> ETradeCredentials | None:
        async with self._transaction():
            return await self._load()

    async def delete(self) -> None:
        async with self._transaction():
            await self._credential_store.delete(self._storage_key)

    async def revoke(self) -> None:
        """Revoke current credentials and delete locally only after broker success.

        This coordinates lifecycle updates, not already-dispatched API requests.
        Missing credentials are a no-op. Broker errors preserve local credentials.
        """
        async with self._transaction():
            credentials = await self._load()
            if credentials is not None:
                await self._oauth_client.revoke_access_token(credentials)
                await self._credential_store.delete(self._storage_key)

    async def record_usage(self, credentials: ETradeCredentials) -> None:
        """Record confirmed usage without overwriting newer or replaced credentials."""
        used_at = self._now()
        async with self._transaction():
            current = await self._load()
            if current is None or not _same_credentials(current, credentials):
                return
            if used_at > current.last_used_at:
                await self._save(current.with_last_used(used_at))

    def status(
        self, credentials: ETradeCredentials | None, *, now: datetime | None = None
    ) -> TokenStatus:
        if credentials is None:
            return TokenStatus.MISSING
        current = (now or self._now()).astimezone(UTC)
        if self._is_expired(credentials, now=current):
            return TokenStatus.EXPIRED
        inactive_after = timedelta(
            seconds=INACTIVITY_SECONDS - self._settings.inactivity_buffer_seconds
        )
        if current - credentials.last_used_at >= inactive_after:
            return TokenStatus.INACTIVE_RENEWABLE
        return TokenStatus.ACTIVE

    def _is_expired(self, credentials: ETradeCredentials, *, now: datetime) -> bool:
        acquired_eastern = credentials.acquired_at.astimezone(EASTERN)
        next_midnight = (acquired_eastern + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return now.astimezone(EASTERN) >= next_midnight

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def _same_credentials(left: ETradeCredentials, right: ETradeCredentials) -> bool:
    return (
        left.access_token == right.access_token
        and left.access_token_secret == right.access_token_secret
        and left.acquired_at == right.acquired_at
    )


class SessionAuthenticator:
    """Transport authenticator backed by SessionManager credentials."""

    def __init__(self, session_manager: SessionManager, oauth_client: OAuthClient) -> None:
        self._session_manager = session_manager
        self._oauth_client = oauth_client

    async def authenticate(self, request: httpx.Request) -> Callable[[], Awaitable[None]]:
        credentials = await self._session_manager.ensure_active()
        self._oauth_client.sign_request(request, credentials)

        async def record_usage() -> None:
            await self._session_manager.record_usage(credentials)

        return record_usage
