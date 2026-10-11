"""Validation shared by directly constructed orders and builder output."""

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from etrade_python.orders import (
    VALID_MARKET_SESSIONS,
    CancelOrderRequest,
    OrderBuilder,
    OrderDetailRequest,
    OrderId,
    OrderInstrumentRequest,
    OrderResponseProduct,
    PlaceOrderRequest,
    PreviewId,
    PreviewOrderRequest,
    PreviewResponseId,
)
from tests.conftest import load_json_fixture


def instrument_payload() -> dict[str, Any]:
    return {
        "Product": {"symbol": "AAPL", "securityType": "EQ"},
        "orderAction": "BUY",
        "quantity": "1",
    }


def detail_payload() -> dict[str, Any]:
    return {
        "priceType": "LIMIT",
        "limitPrice": "10",
        "orderTerm": "GOOD_FOR_DAY",
        "Instrument": [instrument_payload()],
    }


@pytest.mark.parametrize("field", ["orderAction", "quantityType"])
@pytest.mark.parametrize("value", ["UNKNOWN", "INVALID"])
def test_instrument_rejects_unknown_values(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        OrderInstrumentRequest.model_validate({**instrument_payload(), field: value})


@pytest.mark.parametrize("field", ["quantity", "orderedQuantity", "reserveQuantity"])
@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "-Infinity"])
def test_instrument_rejects_invalid_quantities(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        OrderInstrumentRequest.model_validate({**instrument_payload(), field: value})


@pytest.mark.parametrize("quantity_type", ["DOLLAR", "ALL_I_OWN"])
def test_alternative_sizing_keeps_optional_quantity(quantity_type: str) -> None:
    payload = instrument_payload()
    payload.pop("quantity")
    payload["quantityType"] = quantity_type
    assert OrderInstrumentRequest.model_validate(payload).quantity is None


@pytest.mark.parametrize("field", ["priceType", "orderTerm", "marketSession"])
@pytest.mark.parametrize("value", ["UNKNOWN", "INVALID"])
def test_detail_rejects_unknown_values(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        OrderDetailRequest.model_validate({**detail_payload(), field: value})


def test_preview_rejects_unknown_order_type() -> None:
    with pytest.raises(ValidationError):
        PreviewOrderRequest.model_validate(
            {"orderType": "UNKNOWN", "clientOrderId": "test", "Order": [detail_payload()]}
        )


@pytest.mark.parametrize(
    "missing", ["callPut", "expiryYear", "expiryMonth", "expiryDay", "strikePrice"]
)
def test_options_require_contract_fields(missing: str) -> None:
    product: dict[str, Any] = {
        "symbol": "AAPL",
        "securityType": "OPTN",
        "callPut": "CALL",
        "expiryYear": 2026,
        "expiryMonth": 10,
        "expiryDay": 16,
        "strikePrice": "100",
    }
    product.pop(missing)
    with pytest.raises(ValidationError):
        OrderInstrumentRequest.model_validate({**instrument_payload(), "Product": product})


@pytest.mark.parametrize(
    "overrides",
    [
        {"callPut": "INVALID"},
        {"expiryMonth": 13},
        {"expiryDay": 32},
        {"expiryMonth": 2, "expiryDay": 30},
        {"strikePrice": "0"},
        {"strikePrice": "-1"},
        {"strikePrice": "Infinity"},
    ],
)
def test_option_contract_values_are_validated(overrides: dict[str, object]) -> None:
    product = {
        "symbol": "AAPL",
        "securityType": "OPTN",
        "callPut": "CALL",
        "expiryYear": 2026,
        "expiryMonth": 10,
        "expiryDay": 16,
        "strikePrice": "100",
        **overrides,
    }
    with pytest.raises(ValidationError):
        OrderInstrumentRequest.model_validate({**instrument_payload(), "Product": product})


@pytest.mark.parametrize(
    "product",
    [{}, {"symbol": "AAPL"}, {"securityType": "EQ"}, {"symbol": "AAPL", "securityType": "UNKNOWN"}],
)
def test_request_product_requires_symbol_and_supported_type(product: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        OrderInstrumentRequest.model_validate({**instrument_payload(), "Product": product})
    # Response models must still accept incomplete product details.
    OrderResponseProduct.model_validate(product)


@pytest.mark.parametrize("limit_field", ["limitPrice", "stopLimitPrice"])
def test_stop_limit_accepts_either_limit_component(limit_field: str) -> None:
    payload = {**detail_payload(), "priceType": "STOP_LIMIT", "stopPrice": "10"}
    payload.pop("limitPrice")
    payload[limit_field] = "9"
    assert OrderDetailRequest.model_validate(payload).stop_price == Decimal("10")


def test_stop_limit_rejects_missing_limit_component() -> None:
    payload = {**detail_payload(), "priceType": "STOP_LIMIT", "stopPrice": "10"}
    payload.pop("limitPrice")
    with pytest.raises(ValidationError, match="limit_price or stop_limit_price"):
        OrderDetailRequest.model_validate(payload)


@pytest.mark.parametrize(
    "price_type, field",
    [("LIMIT", "limitPrice"), ("STOP", "stopPrice"), ("STOP_LIMIT", "stopLimitPrice")],
)
@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "not-a-price"])
def test_applicable_prices_are_finite_positive_decimals(
    price_type: str, field: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        OrderDetailRequest.model_validate(
            {**detail_payload(), "priceType": price_type, "stopPrice": "10", field: value}
        )


def test_unused_stop_placeholder_is_preserved() -> None:
    detail = OrderDetailRequest.model_validate({**detail_payload(), "stopPrice": ""})
    assert detail.stop_price == ""


def test_exto_and_normalized_values_work_directly_and_with_builder() -> None:
    assert "EXTO" in VALID_MARKET_SESSIONS
    instrument = {
        **instrument_payload(),
        "orderAction": " buy ",
        "Product": {"symbol": " aapl ", "securityType": " eq "},
    }
    direct = PreviewOrderRequest.model_validate(
        {
            "orderType": " eq ",
            "clientOrderId": "test",
            "Order": [
                {
                    **detail_payload(),
                    "allOrNone": "false",
                    "marketSession": " exto ",
                    "Instrument": [instrument],
                }
            ],
        }
    )
    built = (
        OrderBuilder("fake-key")
        .client_order_id("test")
        .quantity_type("QUANTITY")
        .equity_limit("AAPL", action="BUY", quantity=1, limit_price=10)
        .market_session("EXTO")
        .build_preview_request()
    )
    assert direct.request_body() == built.request_body()


@pytest.mark.parametrize(
    "model_type, field",
    [(CancelOrderRequest, "orderId"), (OrderId, "orderId"), (PreviewId, "previewId")],
)
@pytest.mark.parametrize("value", [0, -1, True, False, 1.0, 1.5, "1", Decimal("1"), None])
def test_request_ids_require_positive_python_integers(
    model_type: type[Any], field: str, value: object
) -> None:
    with pytest.raises(ValidationError):
        model_type.model_validate({field: value})


@pytest.mark.parametrize("value", [0, -1, True, 1.0, 1.5, "1", Decimal("1")])
def test_builder_order_id_rejects_noninteger_ids(value: Any) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        OrderBuilder("fake-key").order_id(value)


@pytest.mark.parametrize(
    "model_type, fixture_name, envelope",
    [
        (PreviewOrderRequest, "preview_order_request_equity.json", "PreviewOrderRequest"),
        (PlaceOrderRequest, "place_order_request_equity.json", "PlaceOrderRequest"),
    ],
)
def test_nested_request_validation_cannot_bypass_instrument_rules(
    model_type: type[Any], fixture_name: str, envelope: str
) -> None:
    payload = load_json_fixture(f"responses/{fixture_name}")[envelope]
    payload["Order"][0]["Instrument"][0]["quantity"] = "0"
    with pytest.raises(ValidationError):
        model_type.model_validate(payload)


@pytest.mark.parametrize("value", [0, True, 1.5, "1", Decimal("1")])
def test_placement_rejects_invalid_preview_ids(value: object) -> None:
    payload = load_json_fixture("responses/place_order_request_equity.json")["PlaceOrderRequest"]
    payload["PreviewIds"] = [{"previewId": value}]
    with pytest.raises(ValidationError):
        PlaceOrderRequest.model_validate(payload)


def test_response_preview_id_is_revalidated_for_placement() -> None:
    response_id = PreviewResponseId(previewId=0)
    payload = load_json_fixture("responses/place_order_request_equity.json")["PlaceOrderRequest"]
    payload["PreviewIds"] = [response_id]
    with pytest.raises(ValidationError):
        PlaceOrderRequest.model_validate(payload)
