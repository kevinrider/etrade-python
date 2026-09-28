"""The client composition root."""

import httpx

from etrade_python.accounts.service import AccountsService
from etrade_python.auth.oauth import OAuthClient
from etrade_python.auth.session import SessionAuthenticator, SessionManager
from etrade_python.auth.stores import CredentialStore, KeyringCredentialStore
from etrade_python.config import ETradeSettings
from etrade_python.exceptions import ETradeValidationError
from etrade_python.transport.auth import RequestAuthenticator
from etrade_python.transport.http import ApiTransport
from etrade_python.transport.retry import RetryPolicy


class ETradeClient:
    """Async client lifecycle with one HTTP client shared by auth and services."""

    def __init__(
        self,
        settings: ETradeSettings,
        *,
        authenticator: RequestAuthenticator | None = None,
        credential_store: CredentialStore | None = None,
        profile: str = "default",
        http_client: httpx.AsyncClient | None = None,
        http_transport: httpx.AsyncBaseTransport | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        if http_client is not None and http_transport is not None:
            raise ETradeValidationError("Supply either http_client or http_transport, not both")
        self._owns_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(
            transport=http_transport,
            timeout=settings.request_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        )
        self.oauth = OAuthClient(settings, http_client=self._http_client)
        self.session = SessionManager(
            settings=settings,
            oauth_client=self.oauth,
            credential_store=credential_store or KeyringCredentialStore(),
            profile=profile,
        )
        active_authenticator = authenticator or SessionAuthenticator(self.session, self.oauth)
        self._transport = ApiTransport(
            settings,
            authenticator=active_authenticator,
            http_client=self._http_client,
            retry_policy=retry_policy,
        )
        self.accounts = AccountsService(self._transport)
        self._closed = False

    @classmethod
    def from_environment(cls) -> "ETradeClient":
        """Load ETRADE_ variables; does not read .env files or authenticate."""
        return cls(ETradeSettings())

    async def __aenter__(self) -> "ETradeClient":
        await self._transport.__aenter__()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if not self._closed:
            self._closed = True
            await self._transport.aclose()
            await self.oauth.aclose()
            if self._owns_client:
                await self._http_client.aclose()
