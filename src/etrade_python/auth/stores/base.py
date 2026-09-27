"""Credential store protocol."""

from typing import Protocol

from etrade_python.auth.credentials import ETradeCredentials


class CredentialStore(Protocol):
    """Async persistence boundary for OAuth credentials."""

    async def load(self, profile: str) -> ETradeCredentials | None:
        """Load credentials for a profile, returning None when absent."""

    async def save(self, profile: str, credentials: ETradeCredentials) -> None:
        """Persist credentials for a profile."""

    async def delete(self, profile: str) -> None:
        """Delete credentials for a profile."""
