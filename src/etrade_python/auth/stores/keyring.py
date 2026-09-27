"""Keyring-backed credential store."""

import asyncio
import json

import keyring
from keyring.errors import PasswordDeleteError
from pydantic import ValidationError

from etrade_python.auth.credentials import ETradeCredentials
from etrade_python.exceptions import ETradeValidationError


class KeyringCredentialStore:
    """Store credentials in the user's configured system keyring."""

    def __init__(self, *, service_name: str = "etrade-python") -> None:
        self._service_name = service_name

    async def load(self, profile: str) -> ETradeCredentials | None:
        raw = await asyncio.to_thread(keyring.get_password, self._service_name, profile)
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            return ETradeCredentials.model_validate(data)
        except (json.JSONDecodeError, TypeError, ValidationError):
            raise ETradeValidationError("Stored E*TRADE credentials are invalid") from None

    async def save(self, profile: str, credentials: ETradeCredentials) -> None:
        payload = json.dumps(
            {
                "access_token": credentials.access_token.get_secret_value(),
                "access_token_secret": credentials.access_token_secret.get_secret_value(),
                "acquired_at": credentials.acquired_at.isoformat(),
                "last_used_at": credentials.last_used_at.isoformat(),
                "renewed_at": None
                if credentials.renewed_at is None
                else credentials.renewed_at.isoformat(),
            },
            separators=(",", ":"),
        )
        await asyncio.to_thread(keyring.set_password, self._service_name, profile, payload)

    async def delete(self, profile: str) -> None:
        try:
            await asyncio.to_thread(keyring.delete_password, self._service_name, profile)
        except PasswordDeleteError:
            return
