import json
from decimal import Decimal

import httpx
import pytest

from etrade_python import (
    ETradeClient,
    ETradeResponseError,
    ETradeSettings,
    ETradeValidationError,
    OrdersRequest,
    PlaceOrderRequest,
    PreviewOrderRequest,
)
from etrade_python.orders import OrdersService
from etrade_python.transport import ApiTransport
from tests.conftest import FakeAuthenticator, load_json_fixture


def _preview_request() -> PreviewOrderRequest:
    return PreviewOrderRequest.model_validate(
        load_json_fixture("responses/preview_order_request_equity.json")["PreviewOrderRequest"]
    )


def _place_request() -> PlaceOrderRequest:
    return PlaceOrderRequest.model_validate(
        load_json_fixture("responses/place_order_request_equity.json")["PlaceOrderRequest"]
    )


async def test_orders_list_contract(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/accounts/fake-key/orders.json"
        assert request.url.params == httpx.QueryParams(
            {"count": "10", "status": "OPEN", "fromDate": "01012026"}
        )
        return httpx.Response(200, json=load_json_fixture("responses/orders_response.json"))

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        response = await OrdersService(transport).list(
            "fake-key", OrdersRequest(count=10, status="OPEN", fromDate="01012026")
        )

    assert len(response.orders) == 2
    assert response.marker == "abc"


async def test_orders_list_all_follows_marker(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.params.get("marker") == "abc":
            return httpx.Response(
                200, json=load_json_fixture("responses/orders_response_page2.json")
            )
        return httpx.Response(200, json=load_json_fixture("responses/orders_response.json"))

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        orders = [
            order
            async for order in OrdersService(transport).list_all("fake-key", OrdersRequest(count=2))
        ]

    assert len(calls) == 2
    assert calls[1].url.params.get("marker") == "abc"
    assert len(orders) >= 2


async def test_preview_order_contract(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    request_model = _preview_request()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/accounts/fake-key/orders/preview.json"
        assert json.loads(request.content) == request_model.request_body()
        return httpx.Response(
            200, json=load_json_fixture("responses/preview_order_response_equity.json")
        )

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        response = await OrdersService(transport).preview("fake-key", request_model)

    assert response.preview_ids[0].preview_id == 3429395279
    assert response.total_order_value == Decimal("175.95")


async def test_place_order_contract(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    request_model = _place_request()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/accounts/fake-key/orders/place.json"
        assert json.loads(request.content) == request_model.request_body()
        return httpx.Response(
            200, json=load_json_fixture("responses/place_order_response_equity.json")
        )

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        response = await OrdersService(transport).place("fake-key", request_model)

    assert response.order_ids[0].order_id == 485


async def test_preview_and_place_change_contract(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/change/preview.json"):
            return httpx.Response(
                200, json=load_json_fixture("responses/change_preview_order_response.json")
            )
        return httpx.Response(
            200, json=load_json_fixture("responses/place_change_order_response.json")
        )

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        preview = await OrdersService(transport).preview_change("fake-key", 826, _preview_request())
        placed = await OrdersService(transport).place_change("fake-key", 826, _place_request())

    assert requests[0].method == "PUT"
    assert requests[0].url.path == "/v1/accounts/fake-key/orders/826/change/preview.json"
    assert requests[1].url.path == "/v1/accounts/fake-key/orders/826/change/place.json"
    assert preview.preview_ids[0].preview_id == 926244279
    assert placed.order_ids[0].order_id == 826


async def test_cancel_order_contract(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path == "/v1/accounts/fake-key/orders/cancel.json"
        assert json.loads(request.content) == {"CancelOrderRequest": {"orderId": 11}}
        return httpx.Response(200, json=load_json_fixture("responses/cancel_order_response.json"))

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        response = await OrdersService(transport).cancel("fake-key", 11)

    assert response.order_id == 11


async def test_orders_reject_blank_ids(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    async with ApiTransport(settings, authenticator=auth) as transport:
        service = OrdersService(transport)
        with pytest.raises(ETradeValidationError, match="account_id_key"):
            await service.list(" ")
        with pytest.raises(ETradeValidationError, match="order_id"):
            await service.cancel("fake-key", 0)


async def test_invalid_order_response_is_structured(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])),
    ) as transport:
        with pytest.raises(ETradeResponseError):
            await OrdersService(transport).list("fake-key")


async def test_client_exposes_orders_service(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ETradeClient(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json=load_json_fixture("responses/orders_response.json"))
        ),
    ) as client:
        assert isinstance(client.orders, OrdersService)
        response = await client.orders.list("fake-key")

    assert response.orders[0].order_id == 96


async def test_orders_list_empty_response_returns_empty_page(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(lambda r: httpx.Response(204)),
    ) as transport:
        response = await OrdersService(transport).list("fake-key")

    assert response.orders == []


async def test_invalid_order_envelopes_are_structured(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"PreviewOrderResponse": []})
        ),
    ) as transport:
        with pytest.raises(ETradeResponseError, match="Invalid preview order response"):
            await OrdersService(transport).preview("fake-key", _preview_request())

    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"PlaceOrderResponse": []})
        ),
    ) as transport:
        with pytest.raises(ETradeResponseError, match="Invalid place order response"):
            await OrdersService(transport).place("fake-key", _place_request())

    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"PreviewOrderResponse": []})
        ),
    ) as transport:
        with pytest.raises(ETradeResponseError, match="Invalid preview changed order response"):
            await OrdersService(transport).preview_change("fake-key", 826, _preview_request())

    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"PlaceOrderResponse": []})
        ),
    ) as transport:
        with pytest.raises(ETradeResponseError, match="Invalid place changed order response"):
            await OrdersService(transport).place_change("fake-key", 826, _place_request())

    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"CancelOrderResponse": []})
        ),
    ) as transport:
        with pytest.raises(ETradeResponseError, match="Invalid cancel order response"):
            await OrdersService(transport).cancel("fake-key", 826)


async def test_invalid_order_model_payloads_include_sanitized_diagnostics(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={"PreviewOrderResponse": {"PreviewIds": {"previewId": "bad"}}},
            )
        ),
    ) as transport:
        with pytest.raises(ETradeResponseError, match="Invalid preview order response") as error:
            await OrdersService(transport).preview("fake-key", _preview_request())

    assert "access_token" not in str(error.value)
    assert "PreviewIds" in str(error.value)
