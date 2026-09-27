"""The client composition root. Business services arrive in later milestones."""

import httpx

from etrade_python.config import ETradeSettings
from etrade_python.transport.auth import RequestAuthenticator
from etrade_python.transport.http import ApiTransport
from etrade_python.transport.retry import RetryPolicy


class ETradeClient:
    """Async client lifecycle with a single transport shared by future services."""

    def __init__(
        self,
        settings: ETradeSettings,
        *,
        authenticator: RequestAuthenticator | None = None,
        http_client: httpx.AsyncClient | None = None,
        http_transport: httpx.AsyncBaseTransport | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._transport = ApiTransport(
            settings,
            authenticator=authenticator,
            http_client=http_client,
            http_transport=http_transport,
            retry_policy=retry_policy,
        )

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
        await self._transport.aclose()
