"""Reject malformed IDs before any broker request is sent."""

from decimal import Decimal
from typing import Any

import httpx
import pytest

from etrade_python import (
    ETradeClient,
    ETradeSettings,
    ETradeValidationError,
    PlaceOrderRequest,
    PreviewOrderRequest,
)
from tests.conftest import FakeAuthenticator, load_json_fixture


@pytest.mark.parametrize("value", [0, -1, True, False, 1.0, 1.5, "1", Decimal("1"), None])
async def test_services_reject_invalid_ids_before_http(
    settings: ETradeSettings, auth: FakeAuthenticator, value: Any
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    preview = PreviewOrderRequest.model_validate(
        load_json_fixture("responses/preview_order_request_equity.json")["PreviewOrderRequest"]
    )
    place = PlaceOrderRequest.model_validate(
        load_json_fixture("responses/place_order_request_equity.json")["PlaceOrderRequest"]
    )
    async with ETradeClient(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as client:
        for operation in (
            lambda: client.orders.cancel("fake-key", value),
            lambda: client.orders.preview_change("fake-key", value, preview),
            lambda: client.orders.place_change("fake-key", value, place),
            lambda: client.alerts.get(value),
            lambda: client.alerts.delete(value),
            lambda: client.alerts.delete([1, value]),
        ):
            with pytest.raises(ETradeValidationError):
                await operation()
    assert calls == []
