import httpx
import pytest

from etrade_python import ETradeClient, ETradeSettings, ETradeTransportError, ETradeValidationError
from etrade_python.transport import ApiTransport


class TrackingTransport(httpx.AsyncBaseTransport):
    closed = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError("Construction must not make requests")

    async def aclose(self) -> None:
        self.closed = True


async def test_owned_lifecycle(settings: ETradeSettings) -> None:
    transport = TrackingTransport()
    client = ETradeClient(settings, http_transport=transport)
    assert not transport.closed
    async with client as entered:
        assert entered is client
    assert transport.closed
    await client.aclose()
    with pytest.raises(ETradeTransportError, match="closed"):
        await client.__aenter__()


async def test_borrowed_lifecycle(settings: ETradeSettings) -> None:
    async with httpx.AsyncClient(transport=TrackingTransport()) as http_client:
        async with ETradeClient(settings, http_client=http_client):
            pass
        assert not http_client.is_closed
    assert http_client.is_closed


async def test_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETRADE_CONSUMER_KEY", "fake-key")
    monkeypatch.setenv("ETRADE_CONSUMER_SECRET", "fake-secret")
    async with ETradeClient.from_environment():
        pass


def test_mutually_exclusive_injection(settings: ETradeSettings) -> None:
    client = httpx.AsyncClient()
    with pytest.raises(ETradeValidationError, match="not both"):
        ApiTransport(settings, http_client=client, http_transport=TrackingTransport())
