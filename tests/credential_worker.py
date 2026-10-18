"""Spawned-process fixture: fake keyring persistence and mocked OAuth only."""

import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import keyring
from pydantic import SecretStr

from etrade_python import (
    CredentialCoordinationError,
    ETradeClient,
    ETradeCredentials,
    ETradeSettings,
    KeyringCredentialStore,
)

NOW = datetime(2026, 10, 17, 18, tzinfo=UTC)


def original() -> ETradeCredentials:
    return ETradeCredentials(
        access_token=SecretStr("fake-token"),
        access_token_secret=SecretStr("fake-secret"),
        acquired_at=NOW - timedelta(hours=4),
        last_used_at=NOW - timedelta(hours=3),
    )


async def main() -> None:
    operation, directory, argument = sys.argv[1:]
    root = Path(directory)

    def storage(service: str, username: str) -> Path:
        digest = hashlib.sha256(json.dumps([service, username]).encode()).hexdigest()
        return root / f"{digest}.json"

    def get_password(service: str, username: str) -> str | None:
        path = storage(service, username)
        return path.read_text() if path.exists() else None

    def set_password(service: str, username: str, password: str) -> None:
        storage(service, username).write_text(password)

    def delete_password(service: str, username: str) -> None:
        storage(service, username).unlink(missing_ok=True)

    keyring.get_password = get_password
    keyring.set_password = set_password
    keyring.delete_password = delete_password

    async def forbidden(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Real network forbidden in spawned fixture")

    # Every client below uses MockTransport. Forbid any accidental alternative.
    async def forbid_transport(
        self: httpx.AsyncHTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        return await forbidden(request)

    httpx.AsyncHTTPTransport.handle_async_request = forbid_transport

    async def handler(request: httpx.Request) -> httpx.Response:
        with (root / "broker-calls.txt").open("a") as file:
            file.write(request.url.path + "\n")
        print("BROKER", flush=True)
        await asyncio.to_thread(sys.stdin.readline)
        return httpx.Response(200, text="success")

    store = KeyringCredentialStore(
        lock_directory=root / "locks", lock_timeout_seconds=0.15 if argument == "timeout" else 5
    )
    print("READY", flush=True)
    if operation == "hold":
        async with store.lock(argument):
            print("LOCKED", flush=True)
            await asyncio.to_thread(sys.stdin.readline)
        return

    async with ETradeClient(
        ETradeSettings(consumer_key="fake-key", consumer_secret="fake-consumer-secret"),
        credential_store=store,
        http_transport=httpx.MockTransport(handler),
    ) as client:
        # A fixed clock keeps these tests independent of daily expiration.
        from etrade_python.auth import SessionManager

        client.session = SessionManager(
            settings=ETradeSettings(
                consumer_key="fake-key", consumer_secret="fake-consumer-secret"
            ),
            oauth_client=client.oauth,
            credential_store=store,
            clock=lambda: NOW + timedelta(minutes=int(argument)),
        )
        if operation == "save":
            await client.session.save(original())
        elif operation == "replace":
            await client.session.save(
                original().model_copy(update={"access_token": SecretStr("fake-replacement")})
            )
        elif operation == "usage":
            await client.session.record_usage(original())
        elif operation == "delete":
            await client.session.delete()
        elif operation == "renew":
            await client.session.ensure_active()
        elif operation == "explicit-renew":
            await client.session.renew()
        elif operation == "revoke":
            await client.session.revoke()
        elif operation != "load":
            raise AssertionError("Unknown test operation")
        current = await client.session.load()
        print("DONE " + (current.model_dump_json() if current is not None else "null"), flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except CredentialCoordinationError as error:
        print(type(error).__name__ + ": " + str(error), file=sys.stderr)
        raise SystemExit(2) from None
