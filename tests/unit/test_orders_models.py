from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from etrade_python import (
    CancelOrderResponse,
    Messages,
    OrderDetailRequest,
    OrderInstrument,
    OrderInstrumentRequest,
    OrderLots,
    OrderProduct,
    OrdersRequest,
    OrdersResponse,
    PlaceOrderRequest,
    PlaceOrderResponse,
    PreviewOrderRequest,
    PreviewOrderResponse,
)
from tests.conftest import load_json_fixture


def _preview_request() -> PreviewOrderRequest:
    return PreviewOrderRequest.model_validate(
        load_json_fixture("responses/preview_order_request_equity.json")["PreviewOrderRequest"]
    )


def test_orders_request_query_params() -> None:
    request = OrdersRequest(
        marker="abc",
        count=25,
        status="OPEN",
        fromDate="01012026",
        toDate="01312026",
        symbol="AAPL",
        securityType="EQ",
        transactionType="BUY",
        marketSession="REGULAR",
    )

    assert request.query_params() == {
        "marker": "abc",
        "count": 25,
        "status": "OPEN",
        "fromDate": "01012026",
        "toDate": "01312026",
        "symbol": "AAPL",
        "securityType": "EQ",
        "transactionType": "BUY",
        "marketSession": "REGULAR",
    }


def test_preview_order_request_serializes_envelope() -> None:
    request = _preview_request()

    assert request.request_body() == load_json_fixture(
        "responses/preview_order_request_equity.json"
    )
    assert request.orders[0].limit_price == Decimal("169")
    assert request.orders[0].instruments[0].product.symbol == "FB"


@pytest.mark.parametrize("client_order_id", ["abc123", "A" * 20])
def test_preview_order_request_accepts_valid_client_order_ids(client_order_id: str) -> None:
    payload = load_json_fixture("responses/preview_order_request_equity.json")[
        "PreviewOrderRequest"
    ]
    payload["clientOrderId"] = client_order_id

    request = PreviewOrderRequest.model_validate(payload)

    assert request.client_order_id == client_order_id


@pytest.mark.parametrize(
    "client_order_id",
    ["", " ", "A" * 21, "demo-order", "demo order", "demo_order", "demo$order"],
)
def test_preview_order_request_rejects_invalid_client_order_ids(client_order_id: str) -> None:
    payload = load_json_fixture("responses/preview_order_request_equity.json")[
        "PreviewOrderRequest"
    ]
    payload["clientOrderId"] = client_order_id

    with pytest.raises(ValidationError, match="client_order_id"):
        PreviewOrderRequest.model_validate(payload)


def test_place_order_request_normalizes_preview_ids() -> None:
    request = PlaceOrderRequest.model_validate(
        {
            "orderType": "EQ",
            "clientOrderId": "1fds311",
            "PreviewIds": [3429395279],
            "Order": [
                {
                    "priceType": "LIMIT",
                    "orderTerm": "GOOD_FOR_DAY",
                    "limitPrice": Decimal("169"),
                    "Instrument": [
                        {
                            "Product": {"symbol": "FB", "securityType": "EQ"},
                            "orderAction": "BUY",
                            "quantityType": "QUANTITY",
                            "quantity": Decimal("1"),
                        }
                    ],
                }
            ],
        }
    )

    assert request.preview_ids[0].preview_id == 3429395279
    assert request.request_body()["PlaceOrderRequest"]["PreviewIds"] == [{"previewId": 3429395279}]


def test_order_request_validates_price_shape() -> None:
    with pytest.raises(ValidationError, match="limit_price"):
        OrderDetailRequest(
            priceType="LIMIT",
            orderTerm="GOOD_FOR_DAY",
            Instrument=[
                OrderInstrumentRequest(
                    Product=OrderProduct(symbol="FB", securityType="EQ"),
                    orderAction="BUY",
                    quantity=Decimal("1"),
                )
            ],
        )

    with pytest.raises(ValidationError, match="MARKET"):
        OrderDetailRequest(
            priceType="MARKET",
            orderTerm="GOOD_FOR_DAY",
            limitPrice=Decimal("169"),
            Instrument=[
                OrderInstrumentRequest(
                    Product=OrderProduct(symbol="FB", securityType="EQ"),
                    orderAction="BUY",
                    quantity=Decimal("1"),
                )
            ],
        )


def test_orders_response_parses_fixture() -> None:
    response = OrdersResponse.model_validate(
        load_json_fixture("responses/orders_response.json")["OrdersResponse"]
    )

    assert len(response.orders) == 2
    assert response.orders[0].order_id == 96
    assert response.orders[0].total_order_value == Decimal("1000.0")
    assert response.orders[0].order_details[0].placed_time == datetime(2021, 5, 3, 0, 0, tzinfo=UTC)
    assert response.orders[1].order_details[0].instruments[0].lots is not None
    assert response.orders[1].order_details[0].instruments[0].lots.lots[0].size == Decimal("25")


def test_preview_response_parses_fixture() -> None:
    response = PreviewOrderResponse.model_validate(
        load_json_fixture("responses/preview_order_response_equity.json")["PreviewOrderResponse"]
    )

    assert response.order_type == "EQ"
    assert response.total_order_value == Decimal("175.95")
    assert response.preview_time == datetime(2019, 2, 4, 22, 8, 5, 462000, tzinfo=UTC)
    assert response.preview_ids[0].preview_id == 3429395279
    assert response.orders[0].messages is not None
    assert response.orders[0].messages.messages[0].code == 3041


def test_place_and_cancel_responses_parse_fixtures() -> None:
    placed = PlaceOrderResponse.model_validate(
        load_json_fixture("responses/place_order_response_equity.json")["PlaceOrderResponse"]
    )
    cancelled = CancelOrderResponse.model_validate(
        load_json_fixture("responses/cancel_order_response.json")["CancelOrderResponse"]
    )

    assert placed.order_ids[0].order_id == 485
    assert placed.placed_time == datetime(2019, 2, 4, 22, 8, 19, 447000, tzinfo=UTC)
    assert cancelled.order_id == 11
    assert cancelled.messages is not None
    assert cancelled.messages.messages[0].code == 5011


def test_order_normalizers_accept_single_objects_and_aliases() -> None:
    lots = OrderLots.model_validate({"Lot": {"id": 1, "size": "2"}})
    messages = Messages.model_validate({"Message": {"code": 1, "description": "ok"}})
    instrument = OrderInstrument.model_validate(
        {
            "product": {"symbol": "AAPL", "securityType": "EQ"},
            "Lots": {"Lot": {"id": 1, "size": "2"}},
            "MFQuantity": {"cash": "10"},
        }
    )

    assert lots.lots[0].size == Decimal("2")
    assert messages.messages[0].description == "ok"
    assert instrument.product is not None
    assert instrument.product.symbol == "AAPL"
    assert instrument.lots is not None
    assert instrument.mf_quantity is not None


def test_order_request_validates_more_invalid_shapes() -> None:
    with pytest.raises(ValidationError, match="stop_price"):
        OrderDetailRequest.model_validate(
            {
                "priceType": "STOP",
                "orderTerm": "GOOD_FOR_DAY",
                "Instrument": {
                    "Product": {"symbol": "FB", "securityType": "EQ"},
                    "orderAction": "BUY",
                    "quantity": Decimal("1"),
                },
            }
        )
    with pytest.raises(ValidationError, match="Quantity"):
        OrderInstrumentRequest(
            Product=OrderProduct(symbol="FB", securityType="EQ"),
            orderAction="BUY",
            quantity=Decimal("-1"),
        )
    with pytest.raises(ValidationError, match="nonempty"):
        OrderProduct(symbol=" ", securityType="EQ")


def test_place_order_request_requires_preview_ids() -> None:
    with pytest.raises(ValidationError, match="preview ID"):
        PlaceOrderRequest.model_validate(
            {
                "orderType": "EQ",
                "clientOrderId": "abc123",
                "PreviewIds": [],
                "Order": [
                    {
                        "priceType": "MARKET",
                        "orderTerm": "GOOD_FOR_DAY",
                        "Instrument": [
                            {
                                "Product": {"symbol": "AAPL", "securityType": "EQ"},
                                "orderAction": "BUY",
                                "quantity": "1",
                            }
                        ],
                    }
                ],
            }
        )
