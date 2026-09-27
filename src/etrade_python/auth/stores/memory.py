"""In-memory credential store."""

from etrade_python.auth.credentials import ETradeCredentials


class MemoryCredentialStore:
    """Process-local credential store, mainly for tests and temporary sessions."""

    def __init__(self) -> None:
        self._credentials: dict[str, ETradeCredentials] = {}

    async def load(self, profile: str) -> ETradeCredentials | None:
        return self._credentials.get(profile)

    async def save(self, profile: str, credentials: ETradeCredentials) -> None:
        self._credentials[profile] = credentials

    async def delete(self, profile: str) -> None:
        self._credentials.pop(profile, None)
