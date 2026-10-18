"""Keyring-backed credential store."""

import asyncio
import hashlib
import json
import math
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import keyring
from filelock import BaseFileLock, FileLock, SoftFileLock, Timeout
from keyring.errors import PasswordDeleteError
from platformdirs import user_cache_path
from pydantic import ValidationError

from etrade_python.auth.credentials import ETradeCredentials
from etrade_python.auth.stores._workers import run_worker
from etrade_python.exceptions import CredentialCoordinationError, ETradeValidationError


class KeyringCredentialStore:
    """Store credentials in the user's configured system keyring."""

    def __init__(
        self,
        *,
        service_name: str = "etrade-python",
        lock_directory: Path | None = None,
        lock_timeout_seconds: float = 60.0,
    ) -> None:
        if (
            isinstance(lock_timeout_seconds, bool)
            or not math.isfinite(lock_timeout_seconds)
            or lock_timeout_seconds < 0
        ):
            raise ETradeValidationError("Credential lock timeout must be finite and nonnegative")
        self._service_name = service_name
        self._lock_directory = (
            lock_directory
            if lock_directory is not None
            else user_cache_path("etrade-python") / "credential-locks"
        )
        self._lock_timeout_seconds = lock_timeout_seconds

    @asynccontextmanager
    async def lock(self, namespace: str) -> AsyncGenerator[None]:
        """Hold an OS-backed namespace lock; no credential values are written to disk."""
        digest = hashlib.sha256(
            json.dumps([self._service_name, namespace]).encode("utf-8")
        ).hexdigest()
        # FileLock's runtime alias may select a soft lock on unsupported systems.
        lock_class = cast(type[BaseFileLock], FileLock)
        if issubclass(lock_class, SoftFileLock):
            raise CredentialCoordinationError("OS credential locks are unavailable")
        lock = lock_class(
            self._lock_directory / f"{digest}.lock",
            thread_local=False,
            mode=0o600,
            fallback_to_soft=False,
            preserve_lock_file=True,
        )
        deadline = asyncio.get_running_loop().time() + self._lock_timeout_seconds
        try:
            try:
                await run_worker(
                    self._lock_directory.mkdir, mode=0o700, parents=True, exist_ok=True
                )
                while True:
                    try:
                        await run_worker(lock.acquire, timeout=0)
                        break
                    except Timeout:
                        remaining = deadline - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            raise CredentialCoordinationError(
                                "Timed out coordinating credential access"
                            ) from None
                        await asyncio.sleep(min(0.05, remaining))
            except (OSError, NotImplementedError):
                raise CredentialCoordinationError(
                    "Could not coordinate credential access"
                ) from None
            yield
        finally:
            # Acquisition may finish in a worker after its caller is cancelled.
            if lock.is_locked:
                try:
                    await run_worker(lock.release)
                except OSError:
                    raise CredentialCoordinationError(
                        "Could not release credential coordination lock"
                    ) from None

    async def load(self, profile: str) -> ETradeCredentials | None:
        raw = await run_worker(keyring.get_password, self._service_name, profile)
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
        await run_worker(keyring.set_password, self._service_name, profile, payload)

    async def delete(self, profile: str) -> None:
        try:
            await run_worker(keyring.delete_password, self._service_name, profile)
        except PasswordDeleteError:
            return
