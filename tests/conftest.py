import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from etrade_python import ETradeSettings


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for name in os.environ:
        if name.startswith("ETRADE_"):
            monkeypatch.delenv(name)


@pytest.fixture
def settings() -> ETradeSettings:
    return ETradeSettings(consumer_key="fake-key", consumer_secret="fake-secret")


class FakeAuthenticator:
    def __init__(self) -> None:
        self.calls = 0

    async def authenticate(self, request: httpx.Request) -> None:
        self.calls += 1
        request.headers["Authorization"] = (
            f'OAuth oauth_token="fake-token", oauth_token_secret="fake-token-secret", '
            f'oauth_signature="fake-signature-{self.calls}", oauth_verifier="fake-verifier"'
        )


@pytest.fixture
def auth() -> FakeAuthenticator:
    return FakeAuthenticator()


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Fail tests that accidentally bypass MockTransport, before DNS or socket I/O.
    async def forbidden(*args: object, **kwargs: object) -> httpx.Response:
        raise AssertionError("Real network calls are forbidden in the offline suite")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    yield


def load_json_fixture(path: str) -> Any:
    fixture_path = Path(__file__).parent / "fixtures" / path
    with fixture_path.open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)
