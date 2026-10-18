import asyncio
import hashlib
import json
import sys
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from filelock import FileLock, SoftFileLock

from etrade_python import (
    CoordinatedCredentialStore,
    CredentialCoordinationError,
    ETradeApiError,
    ETradeClient,
    ETradeCredentials,
    ETradeSettings,
    ETradeValidationError,
    KeyringCredentialStore,
    MemoryCredentialStore,
    OAuthClient,
    SessionManager,
)
from etrade_python.auth.stores._workers import run_worker
from tests.credential_worker import NOW, original

ROOT = Path(__file__).resolve().parents[2]


async def start(operation: str, directory: Path, argument: str = "0") -> asyncio.subprocess.Process:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "tests.credential_worker",
        operation,
        str(directory),
        argument,
        cwd=ROOT,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdout is not None
    assert await asyncio.wait_for(process.stdout.readline(), 10) == b"READY\n"
    return process


async def finish(process: asyncio.subprocess.Process, expected: int = 0) -> str:
    try:
        out, error = await asyncio.wait_for(process.communicate(b"\n"), 10)
        assert process.returncode == expected, error.decode()
        return out.decode() + error.decode()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def run(operation: str, directory: Path, argument: str = "0") -> Any:
    output = await finish(await start(operation, directory, argument))
    return json.loads(output.split("DONE ")[1])


@pytest.mark.parametrize("operation, broker_calls", [("renew", 1), ("explicit-renew", 2)])
async def test_process_renewals_are_coordinated(
    tmp_path: Path, operation: str, broker_calls: int
) -> None:
    await run("save", tmp_path)
    first = await start(operation, tmp_path)
    assert first.stdout is not None
    assert await asyncio.wait_for(first.stdout.readline(), 5) == b"BROKER\n"
    second = await start(operation, tmp_path)
    try:
        assert second.stdout is not None
        # It must wait for the first transaction, not issue another OAuth call.
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(second.stdout.readline(), 0.1)
        await asyncio.gather(finish(first), finish(second))
    finally:
        for process in (first, second):
            if process.returncode is None:
                process.kill()
                await process.wait()
    assert len((tmp_path / "broker-calls.txt").read_text().splitlines()) == broker_calls


@pytest.mark.parametrize(
    "first_action, second_action", [("renew", "delete"), ("revoke", "replace")]
)
async def test_process_oauth_transaction_finishes_before_replacement(
    tmp_path: Path, first_action: str, second_action: str
) -> None:
    await run("save", tmp_path)
    first = await start(first_action, tmp_path)
    assert first.stdout is not None
    assert await asyncio.wait_for(first.stdout.readline(), 5) == b"BROKER\n"
    second = await start(second_action, tmp_path)
    try:
        assert second.stdout is not None
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(second.stdout.readline(), 0.1)
        await finish(first)
        await finish(second)
    finally:
        for process in (first, second):
            if process.returncode is None:
                process.kill()
                await process.wait()
    if second_action == "delete":
        assert await run("load", tmp_path) is None
    else:

        def replacement_written() -> bool:
            return any("fake-replacement" in p.read_text() for p in tmp_path.glob("*.json"))

        assert await asyncio.to_thread(replacement_written)


@pytest.mark.parametrize("change", ["replace", "delete", "revoke"])
async def test_late_process_usage_cannot_restore_credentials(tmp_path: Path, change: str) -> None:
    await run("save", tmp_path)
    expected = await run(change, tmp_path)
    assert await run("usage", tmp_path, "3") == expected


async def test_process_usage_and_stale_save_preserve_newer_timestamps(tmp_path: Path) -> None:
    await run("save", tmp_path)
    await asyncio.gather(run("usage", tmp_path, "2"), run("usage", tmp_path, "1"))
    current = await run("load", tmp_path)
    assert ETradeCredentials.model_validate(current).last_used_at == NOW + timedelta(minutes=2)
    assert await run("save", tmp_path) == current
    await run("explicit-renew", tmp_path, "3")
    renewed = await run("load", tmp_path)
    assert await run("save", tmp_path) == renewed


async def test_process_timeout_namespace_isolation_and_crash_recovery(tmp_path: Path) -> None:
    holder = await start("hold", tmp_path, "shared")
    assert holder.stdout is not None
    assert await asyncio.wait_for(holder.stdout.readline(), 5) == b"LOCKED\n"
    try:
        # A different namespace proceeds while the first is held.
        other = await start("hold", tmp_path, "other")
        assert other.stdout is not None
        assert await asyncio.wait_for(other.stdout.readline(), 5) == b"LOCKED\n"
        await finish(other)
        store = KeyringCredentialStore(lock_directory=tmp_path / "locks", lock_timeout_seconds=0)
        with pytest.raises(CredentialCoordinationError, match="Timed out"):
            async with store.lock("shared"):
                pytest.fail("Must not acquire another process's lock")
    finally:
        holder.kill()
        await holder.wait()
    async with store.lock("shared"):
        pass
    # Persistent lock files contain no credentials and need no stale-file deletion.
    assert list((tmp_path / "locks").glob("*.lock"))
    assert all(b"fake-" not in p.read_bytes() for p in (tmp_path / "locks").glob("*.lock"))


async def test_memory_store_coordinates_distinct_managers(settings: ETradeSettings) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return httpx.Response(200, text="renewed")

    store = MemoryCredentialStore()
    assert isinstance(store, CoordinatedCredentialStore)
    async with OAuthClient(settings, http_transport=httpx.MockTransport(handler)) as oauth:
        managers = [
            SessionManager(
                settings=settings, oauth_client=oauth, credential_store=store, clock=lambda: NOW
            )
            for _ in range(2)
        ]
        await managers[0].save(original())
        await asyncio.gather(*(manager.ensure_active() for manager in managers))
        assert calls == 1


async def test_revocation_failure_preserves_credentials_and_releases_lock(
    settings: ETradeSettings,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"Error": {"code": 1, "message": "synthetic"}})

    store = MemoryCredentialStore()
    async with OAuthClient(settings, http_transport=httpx.MockTransport(handler)) as oauth:
        manager = SessionManager(settings=settings, oauth_client=oauth, credential_store=store)
        await manager.save(original())
        with pytest.raises(ETradeApiError):
            await manager.revoke()
        assert await manager.load() == original()
        await manager.delete()


async def test_explicit_renewal_preserves_timestamps_after_clock_rollback(
    settings: ETradeSettings,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="renewed")

    credentials = original().model_copy(
        update={
            "last_used_at": NOW + timedelta(minutes=5),
            "renewed_at": NOW + timedelta(minutes=6),
        }
    )
    async with OAuthClient(settings, http_transport=httpx.MockTransport(handler)) as oauth:
        manager = SessionManager(
            settings=settings,
            oauth_client=oauth,
            credential_store=MemoryCredentialStore(),
            clock=lambda: NOW,
        )
        await manager.save(credentials)
        renewed = await manager.renew()
        assert renewed.last_used_at == credentials.last_used_at
        assert renewed.renewed_at == credentials.renewed_at


async def test_legacy_store_remains_supported(settings: ETradeSettings) -> None:
    class LegacyStore:
        def __init__(self) -> None:
            self.value: ETradeCredentials | None = None

        async def load(self, profile: str) -> ETradeCredentials | None:
            return self.value

        async def save(self, profile: str, credentials: ETradeCredentials) -> None:
            self.value = credentials

        async def delete(self, profile: str) -> None:
            self.value = None

    store = LegacyStore()
    assert not isinstance(store, CoordinatedCredentialStore)
    async with OAuthClient(settings) as oauth:
        manager = SessionManager(settings=settings, oauth_client=oauth, credential_store=store)
        await manager.save(original())
        assert await manager.load() == original()
        await manager.delete()
        assert await manager.load() is None
        await manager.revoke()  # Missing credentials do not call OAuth.


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan"), True])
def test_invalid_lock_timeout(value: float) -> None:
    with pytest.raises(ETradeValidationError, match="timeout"):
        KeyringCredentialStore(lock_timeout_seconds=value)


async def test_lock_errors_are_sanitized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "fake-private-value"
    directory.write_text("not a directory")
    store = KeyringCredentialStore(lock_directory=directory)
    with pytest.raises(CredentialCoordinationError, match="Could not coordinate") as error:
        async with store.lock("fake-token"):
            pass
    assert "fake-" not in str(error.value)

    def unsupported(self: FileLock) -> None:
        raise NotImplementedError("fake-secret")

    monkeypatch.setattr(type(FileLock(tmp_path / "unused")), "_acquire", unsupported)
    with pytest.raises(CredentialCoordinationError, match="Could not coordinate") as error:
        async with KeyringCredentialStore(lock_directory=tmp_path).lock("fake-token"):
            pass
    assert "fake-secret" not in str(error.value)


async def test_soft_lock_fallback_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("etrade_python.auth.stores.keyring.FileLock", SoftFileLock)
    with pytest.raises(CredentialCoordinationError, match="OS credential locks"):
        async with KeyringCredentialStore(lock_directory=tmp_path).lock("shared"):
            pass


async def test_client_preserves_coordination_error_before_broker_dispatch(
    settings: ETradeSettings, tmp_path: Path
) -> None:
    store = KeyringCredentialStore(lock_directory=tmp_path, lock_timeout_seconds=0)
    fingerprint = hashlib.sha256(settings.consumer_key.get_secret_value().encode()).hexdigest()
    namespace = f"sandbox:{fingerprint}:default"

    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("Coordination failure must prevent broker dispatch")

    async with store.lock(namespace):
        async with ETradeClient(
            settings, credential_store=store, http_transport=httpx.MockTransport(forbidden)
        ) as client:
            with pytest.raises(CredentialCoordinationError, match="Timed out"):
                await client.accounts.list()


async def test_cancelled_waiter_and_exception_release_lock(tmp_path: Path) -> None:
    store = KeyringCredentialStore(lock_directory=tmp_path)
    waiting = asyncio.Event()

    async def contender() -> None:
        waiting.set()
        async with store.lock("shared"):
            pytest.fail("Cancelled waiter must not enter")

    async with store.lock("shared"):
        task = asyncio.create_task(contender())
        await waiting.wait()
        await asyncio.sleep(0.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    with pytest.raises(ValueError):
        async with store.lock("shared"):
            raise ValueError("synthetic")
    async with store.lock("shared"):
        pass


async def test_cancelled_acquisition_worker_releases_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered = threading.Event()
    release = threading.Event()
    acquire = FileLock.acquire

    def blocked_acquire(self: FileLock, *args: Any, **kwargs: Any) -> Any:
        result = acquire(self, *args, **kwargs)
        entered.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(FileLock, "acquire", blocked_acquire)
    store = KeyringCredentialStore(lock_directory=tmp_path, lock_timeout_seconds=0)

    async def lock() -> None:
        async with store.lock("shared"):
            pytest.fail("Cancelled acquisition must not enter the transaction")

    task = asyncio.create_task(lock())
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with store.lock("shared"):
        pass


async def test_lock_release_failure_is_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = FileLock.release
    fails = True

    def failing_release(self: FileLock, force: bool = False) -> None:
        nonlocal fails
        release(self, force)
        if fails:
            fails = False
            raise OSError("fake-private-path")

    monkeypatch.setattr(FileLock, "release", failing_release)
    store = KeyringCredentialStore(lock_directory=tmp_path)
    with pytest.raises(CredentialCoordinationError, match="Could not release") as error:
        async with store.lock("shared"):
            pass
    assert "fake-private" not in str(error.value)
    async with store.lock("shared"):
        pass


async def test_default_lock_directory_and_service_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def cache(appname: str) -> Path:
        return tmp_path / appname

    monkeypatch.setattr("etrade_python.auth.stores.keyring.user_cache_path", cache)
    store = KeyringCredentialStore(service_name="fake-service")
    assert not (tmp_path / "etrade-python").exists()
    async with store.lock("fake-private-profile"):
        async with KeyringCredentialStore(service_name="other-service").lock(
            "fake-private-profile"
        ):
            pass
    paths = list((tmp_path / "etrade-python" / "credential-locks").glob("*.lock"))
    assert len(paths) == 2
    assert all(len(path.stem) == 64 and "fake-" not in str(path) for path in paths)


async def test_cancelled_keyring_write_finishes_before_unlock(
    settings: ETradeSettings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data: dict[str, str] = {}
    entered = threading.Event()
    release = threading.Event()

    def save(service: str, profile: str, payload: str) -> None:
        entered.set()
        assert release.wait(5)
        data[profile] = payload

    def load(service: str, profile: str) -> str | None:
        return data.get(profile)

    def delete(service: str, profile: str) -> None:
        data.pop(profile, None)

    monkeypatch.setattr("keyring.get_password", load)
    monkeypatch.setattr("keyring.set_password", save)
    monkeypatch.setattr("keyring.delete_password", delete)
    async with OAuthClient(settings) as oauth:
        managers = [
            SessionManager(
                settings=settings,
                oauth_client=oauth,
                credential_store=KeyringCredentialStore(lock_directory=tmp_path),
            )
            for _ in range(2)
        ]
        saving = asyncio.create_task(managers[0].save(original()))
        assert await asyncio.to_thread(entered.wait, 5)
        saving.cancel()
        await asyncio.sleep(0)
        saving.cancel()
        deleting = asyncio.create_task(managers[1].delete())
        try:
            await asyncio.sleep(0.05)
            assert not saving.done()
            assert not deleting.done()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await saving
        await deleting
        assert await managers[0].load() is None


async def test_event_loop_shutdown_waits_for_keyring_worker(
    settings: ETradeSettings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data: dict[str, str] = {}
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    errors: list[BaseException] = []

    def save(service: str, profile: str, payload: str) -> None:
        entered.set()
        assert release.wait(5)
        data[profile] = payload

    def load(service: str, profile: str) -> str | None:
        return data.get(profile)

    def delete(service: str, profile: str) -> None:
        data.pop(profile, None)

    monkeypatch.setattr("keyring.get_password", load)
    monkeypatch.setattr("keyring.set_password", save)
    monkeypatch.setattr("keyring.delete_password", delete)

    async def shutdown() -> None:
        async with OAuthClient(settings) as oauth:
            manager = SessionManager(
                settings=settings,
                oauth_client=oauth,
                credential_store=KeyringCredentialStore(lock_directory=tmp_path),
            )
            saving = asyncio.create_task(manager.save(original()))
            assert await asyncio.to_thread(entered.wait, 5)
            assert not saving.done()
        # Return with a pending save: asyncio.run now cancels *all* its Tasks.

    def runner() -> None:
        try:
            asyncio.run(shutdown())
        except BaseException as error:
            errors.append(error)
        finally:
            finished.set()

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    assert await asyncio.to_thread(entered.wait, 5)
    async with OAuthClient(settings) as oauth:
        manager = SessionManager(
            settings=settings,
            oauth_client=oauth,
            credential_store=KeyringCredentialStore(lock_directory=tmp_path),
        )
        deleting = asyncio.create_task(manager.delete())
        try:
            await asyncio.sleep(0.1)
            assert not deleting.done()
        finally:
            release.set()
        await deleting
        assert await asyncio.to_thread(finished.wait, 5)
        await asyncio.to_thread(thread.join, 5)
        assert not errors
        assert await manager.load() is None


@pytest.mark.parametrize("fails", [False, True])
async def test_worker_cancellation_waits_for_completion(fails: bool) -> None:
    entered = threading.Event()
    release = threading.Event()

    def worker() -> int:
        entered.set()
        assert release.wait(5)
        if fails:
            raise OSError("synthetic worker failure")
        return 1

    task = asyncio.create_task(run_worker(worker))
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
