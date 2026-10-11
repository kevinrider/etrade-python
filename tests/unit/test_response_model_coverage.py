"""Regression coverage against a captured inventory of official response fields."""

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import cast

import pytest
from pydantic import BaseModel, ValidationError

from etrade_python.market import models as market
from etrade_python.orders import models as orders
from etrade_python.portfolio import models as portfolio
from tests.conftest import load_json_fixture

_MODELS: dict[tuple[str, str], type[BaseModel]] = {
    ("portfolio", "AccountPortfolio"): portfolio.AccountPortfolio,
    ("portfolio", "CompleteView"): portfolio.CompleteView,
    ("portfolio", "FundamentalView"): portfolio.FundamentalView,
    ("portfolio", "OptionsWatchView"): portfolio.OptionsWatchView,
    ("portfolio", "PerformanceView"): portfolio.PerformanceView,
    ("portfolio", "PortfolioResponse"): portfolio.PortfolioResponse,
    ("portfolio", "Position"): portfolio.Position,
    ("portfolio", "PositionLot"): portfolio.PositionLot,
    ("portfolio", "Product"): portfolio.PortfolioProduct,
    ("portfolio", "ProductId"): portfolio.ProductId,
    ("portfolio", "QuickView"): portfolio.QuickView,
    ("portfolio", "Totals"): portfolio.PortfolioTotals,
    ("quote", "AllQuoteDetails"): market.QuoteDetails,
    ("quote", "ExtendedHourQuoteDetail"): market.ExtendedHourQuoteDetails,
    ("quote", "FundamentalQuoteDetails"): market.QuoteDetails,
    ("quote", "IntradayQuoteDetails"): market.QuoteDetails,
    ("quote", "Message"): market.QuoteMessage,
    ("quote", "Messages"): market.QuoteMessages,
    ("quote", "MutualFund"): market.MutualFundQuoteDetails,
    ("quote", "NetAsset"): market.NetAsset,
    ("quote", "OptionDeliverable"): market.OptionDeliverable,
    ("quote", "OptionGreeks"): market.OptionGreeks,
    ("quote", "OptionQuoteDetails"): market.QuoteDetails,
    ("quote", "Product"): market.Product,
    ("quote", "ProductId"): market.ProductId,
    ("quote", "QuoteData"): market.Quote,
    ("quote", "QuoteResponse"): market.QuotesResponse,
    ("quote", "Redemption"): market.Redemption,
    ("quote", "SaleChargeValues"): market.SaleChargeValues,
    ("quote", "Values"): market.RedemptionValues,
    ("quote", "Week52QuoteDetails"): market.QuoteDetails,
    ("order", "CancelOrderResponse"): orders.CancelOrderResponse,
    ("order", "CashBuyingPowerDetails"): orders.CashBuyingPowerDetails,
    ("order", "Disclosure"): orders.Disclosure,
    ("order", "DtBuyingPowerDetails"): orders.DtBuyingPowerDetails,
    ("order", "Event"): orders.OrderEvent,
    ("order", "Events"): orders.Events,
    ("order", "Instrument"): orders.OrderInstrument,
    ("order", "Lot"): orders.OrderLot,
    ("order", "Lots"): orders.OrderLots,
    ("order", "MFQuantity"): orders.MFQuantity,
    ("order", "MarginBuyingPowerDetails"): orders.MarginBuyingPowerDetails,
    ("order", "Message"): orders.Message,
    ("order", "Messages"): orders.Messages,
    ("order", "Order"): orders.Order,
    ("order", "OrderBuyPowerEffect"): orders.OrderBuyPowerEffect,
    ("order", "OrderDetail"): orders.OrderDetail,
    ("order", "OrderId"): orders.OrderResponseId,
    ("order", "OrdersResponse"): orders.OrdersResponse,
    ("order", "PlaceOrderResponse"): orders.PlaceOrderResponse,
    ("order", "PortfolioMargin"): orders.PortfolioMargin,
    ("order", "PreviewId"): orders.PreviewResponseId,
    ("order", "PreviewOrderResponse"): orders.PreviewOrderResponse,
    ("order", "Product"): orders.OrderResponseProduct,
    ("order", "ProductId"): orders.OrderProductId,
}

# Existing public serialization aliases remain stable even where docs differ.
_ALIASES: dict[tuple[str, str], dict[str, str]] = {
    ("portfolio", "Position"): {"quotestatus": "quoteStatus"},
    ("order", "Instrument"): {"product": "Product"},
    ("order", "OrderDetail"): {"instrument": "Instrument"},
    ("order", "PreviewOrderResponse"): {
        "order": "Order",
        "previewIds": "PreviewIds",
        "disclosure": "Disclosure",
    },
    ("order", "PlaceOrderResponse"): {"order": "Order", "orderIds": "OrderIds"},
}


def assert_only_modeled_fields(value: object) -> None:
    """Response models must expose only declared fields at every nesting level."""
    if isinstance(value, BaseModel):
        assert not hasattr(value, "broker_metadata")
        assert not value.model_extra
        assert "broker_metadata" not in type(value).model_json_schema()["properties"]
        for name in type(value).model_fields:
            assert_only_modeled_fields(getattr(value, name))
    elif isinstance(value, list):
        for item in cast(list[object], value):
            assert_only_modeled_fields(item)


@pytest.mark.parametrize("domain, documented_model", list(_MODELS))
def test_documented_response_fields_are_typed_and_in_schema(
    domain: str,
    documented_model: str,
) -> None:
    inventory = load_json_fixture("documented_response_fields.json")
    samples = load_json_fixture("responses/documented_model_samples.json")
    model_type = _MODELS[(domain, documented_model)]
    payload = {
        **samples[domain][documented_model],
        "futureResponseField": "discarded",
        "broker_metadata": {"legacyField": "discarded"},
    }
    instance = model_type.model_validate(payload)
    assert not hasattr(instance, "futureResponseField")
    assert "futureResponseField" not in instance.model_dump(by_alias=True)
    assert_only_modeled_fields(instance)
    schema = model_type.model_json_schema(by_alias=True)
    aliases = _ALIASES.get((domain, documented_model), {})
    fields = {field.alias or name: name for name, field in model_type.model_fields.items()}
    documented_fields = cast(dict[str, str], inventory[domain][documented_model])
    for broker_name, broker_type in documented_fields.items():
        alias = aliases.get(broker_name, broker_name)
        assert alias in schema["properties"], broker_name
        attribute = getattr(instance, fields[alias])
        assert attribute is not None, broker_name
        if broker_type.startswith("number"):
            assert isinstance(attribute, Decimal), broker_name
        elif broker_type.startswith("integer"):
            assert isinstance(attribute, (int, date, datetime)), broker_name
        elif broker_type == "boolean":
            assert isinstance(attribute, bool), broker_name
        elif broker_type == "string":
            assert isinstance(attribute, (str, date, datetime)), broker_name
        elif broker_type.startswith("array["):
            assert isinstance(attribute, list), broker_name
        else:
            assert isinstance(attribute, BaseModel), broker_name
    model_type.model_validate_json(instance.model_dump_json(by_alias=True))


@pytest.mark.parametrize("domain, documented_model", list(_MODELS))
def test_optional_response_fields_have_safe_defaults(domain: str, documented_model: str) -> None:
    model_type = _MODELS[(domain, documented_model)]
    if model_type in (orders.PreviewResponseId, orders.OrderResponseId):
        with pytest.raises(ValidationError):
            model_type.model_validate({})
        return
    instance = model_type.model_validate({})
    assert_only_modeled_fields(instance)


@pytest.mark.parametrize("spelling", ["quotestatus", "quoteStatus", "both"])
def test_portfolio_quote_status_aliases(spelling: str) -> None:
    sample = load_json_fixture("responses/documented_model_samples.json")["portfolio"]["Position"]
    sample.pop("quotestatus")
    if spelling in {"quotestatus", "both"}:
        sample["quotestatus"] = "DELAYED"
    if spelling in {"quoteStatus", "both"}:
        sample["quoteStatus"] = "REALTIME"
    position = portfolio.Position.model_validate(sample)
    assert position.quote_status == ("DELAYED" if spelling == "quotestatus" else "REALTIME")
    assert not hasattr(position, "broker_metadata")
    assert position.model_dump(by_alias=True)["quoteStatus"] == position.quote_status


@pytest.mark.parametrize("capitalized", [False, True])
def test_quote_nested_aliases(capitalized: bool) -> None:
    sample = load_json_fixture("responses/quote_details_response.json")["QuoteResponse"]
    if capitalized:
        sample["QuoteData"] = sample.pop("quoteData")
        sample["Messages"] = sample.pop("messages")
        sample["Messages"]["Message"] = sample["Messages"].pop("message")
        quote = sample["QuoteData"][0]
        for source in ("all", "option", "mutualFund"):
            quote[source[0].upper() + source[1:]] = quote.pop(source)
        all_details = quote["All"]
        for source in ("ehQuote", "optionDeliverableList"):
            all_details[source[0].upper() + source[1:]] = all_details.pop(source)
        quote["Option"]["OptionGreeks"] = quote["Option"].pop("optionGreeks")
        fund = quote["MutualFund"]
        for source in ("netAssets", "redemption", "deferredSalesCharges", "frontEndSalesCharges"):
            fund[source[0].upper() + source[1:]] = fund.pop(source)
        for source in ("frontEndValues", "salesValues"):
            fund["Redemption"][source[0].upper() + source[1:]] = fund["Redemption"].pop(source)
    response = market.QuotesResponse.model_validate(sample)
    assert_only_modeled_fields(response)
    assert isinstance(response.quotes[0].mutual_fund, market.QuoteDetails)


@pytest.mark.parametrize("shape", ["list", "single", "null", "empty", "wrapper", "wrapper-list"])
def test_quote_collection_shapes(shape: str) -> None:
    values = {"low": "0", "high": "1000", "percent": "1.25"}
    charges = {"lowhigh": "0-1000", "percent": "1.25"}
    deliverable = {"rootSymbol": "EXAMPLE", "deliverableWholeShares": 100}
    message = {"code": 0, "description": "Success"}

    def shaped(item: Mapping[str, object], wrapper: str) -> object:
        if shape == "single":
            return item
        if shape == "null":
            return None
        if shape == "empty":
            return {}
        if shape == "wrapper":
            return {wrapper: item}
        if shape == "wrapper-list":
            return {wrapper: [item]}
        return [item]

    fund = market.MutualFundQuoteDetails.model_validate(
        {
            "optionDeliverableList": shaped(deliverable, "OptionDeliverable"),
            "deferredSalesCharges": shaped(charges, "SaleChargeValues"),
            "frontEndSalesCharges": shaped(charges, "saleChargeValues"),
            "redemption": {
                "frontEndValues": shaped(values, "Values"),
                "salesValues": shaped(values, "values"),
            },
        }
    )
    expected_count = 0 if shape in {"null", "empty"} else 1
    assert len(fund.option_deliverables) == expected_count
    assert len(fund.deferred_sales_charges) == expected_count
    assert len(fund.front_end_sales_charges) == expected_count
    assert fund.redemption is not None
    assert len(fund.redemption.front_end_values) == expected_count
    assert len(fund.redemption.sales_values) == expected_count
    # Message is the container wrapper itself, unlike a list-valued field.
    message_value = message if shape in {"wrapper", "wrapper-list"} else shaped(message, "unused")
    messages = market.QuoteMessages.model_validate({"Message": message_value})
    assert len(messages.messages) == expected_count
    assert_only_modeled_fields(fund)


@pytest.mark.parametrize("capitalized", [False, True])
def test_order_response_nested_aliases(capitalized: bool) -> None:
    for name, model_type in (
        ("PreviewOrderResponse", orders.PreviewOrderResponse),
        ("PlaceOrderResponse", orders.PlaceOrderResponse),
    ):
        sample = load_json_fixture("responses/documented_model_samples.json")["order"][name]
        if capitalized:
            for source in (
                "order",
                "previewIds",
                "orderIds",
                "portfolioMargin",
                "disclosure",
                "marginBpDetails",
                "cashBpDetails",
                "dtBpDetails",
                "messageList",
            ):
                if source in sample:
                    sample[source[0].upper() + source[1:]] = sample.pop(source)
            for source in ("MarginBpDetails", "DtBpDetails"):
                if source in sample:
                    for field in ("marginable", "nonMarginable"):
                        sample[source][field[0].upper() + field[1:]] = sample[source].pop(field)
            if "CashBpDetails" in sample:
                for field in ("settled", "settledUnsettled"):
                    sample["CashBpDetails"][field[0].upper() + field[1:]] = sample[
                        "CashBpDetails"
                    ].pop(field)
        assert_only_modeled_fields(model_type.model_validate(sample))


@pytest.mark.parametrize(
    "shape", ["single", "scalar", "scalar-list", "wrapper", "lower-wrapper", "null", "empty"]
)
def test_order_response_id_collection_shapes(shape: str) -> None:
    for key, wrapper, model_type, attr in (
        ("previewId", "PreviewIds", orders.PreviewOrderResponse, "preview_ids"),
        ("orderId", "OrderIds", orders.PlaceOrderResponse, "order_ids"),
    ):
        item = {key: 7, "cashMargin": "CASH"}
        shapes: dict[str, object] = {
            "single": item,
            "scalar": 7,
            "scalar-list": [7],
            "wrapper": {key[0].upper() + key[1:]: item},
            "lower-wrapper": {key: [item]},
            "null": None,
            "empty": {},
        }
        instance = model_type.model_validate({wrapper: shapes[shape]})
        ids = cast(list[BaseModel], getattr(instance, attr))
        assert len(ids) == (0 if shape in {"null", "empty"} else 1)
        if ids:
            assert getattr(ids[0], "preview_id" if key == "previewId" else "order_id") == 7
        assert_only_modeled_fields(instance)


@pytest.mark.parametrize(
    "model_type, payload",
    [
        (market.MutualFundQuoteDetails, {"netAssets": {"value": "invalid-secret"}}),
        (market.QuoteDetails, {"optionGreeks": {"delta": "invalid-secret"}}),
        (orders.PreviewOrderResponse, {"cashBpDetails": {"settled": {"netBp": "invalid-secret"}}}),
    ],
)
def test_nested_financial_fields_validate(
    model_type: type[BaseModel], payload: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        model_type.model_validate(payload)


def test_response_only_fields_do_not_enter_order_requests() -> None:
    preview_id = orders.PreviewResponseId(previewId=7, cashMargin="CASH")
    product = orders.OrderResponseProduct.model_validate(
        {
            "symbol": "AAPL",
            "securityType": "EQ",
            "productId": {"symbol": "AAPL", "typeCode": "EQUITY"},
        }
    )
    payload = load_json_fixture("responses/place_order_request_equity.json")["PlaceOrderRequest"]
    payload["PreviewIds"] = [preview_id]
    payload["Order"][0]["Instrument"][0]["Product"] = product
    request = orders.PlaceOrderRequest.model_validate(payload)
    body = request.request_body()["PlaceOrderRequest"]
    assert body["PreviewIds"] == [{"previewId": 7}]
    assert body["Order"][0]["Instrument"][0]["Product"] == {"symbol": "AAPL", "securityType": "EQ"}
    assert isinstance(preview_id, orders.PreviewId)
    assert isinstance(product, orders.OrderProduct)


def test_order_responses_accept_existing_model_instances() -> None:
    instrument = orders.OrderInstrument.model_validate(
        {"Product": orders.OrderProduct(symbol="AAPL", securityType="EQ")}
    )
    assert instrument.product is not None
    assert instrument.product.symbol == "AAPL"
    assert instrument.product.product_id is None
    for ids in (orders.PreviewId(previewId=7), [orders.PreviewId(previewId=7)]):
        response = orders.PreviewOrderResponse.model_validate({"PreviewIds": ids})
        assert response.preview_ids[0].preview_id == 7
        assert response.preview_ids[0].cash_margin is None
    placed = orders.PlaceOrderResponse.model_validate({"OrderIds": [orders.OrderId(orderId=7)]})
    assert placed.order_ids[0].order_id == 7


def test_response_ids_discard_unknown_fields() -> None:
    preview = orders.PreviewResponseId.model_validate(
        {
            "previewId": 7,
            "cashMargin": "CASH",
            "futurePreviewField": "preserved",
        }
    )
    order = orders.OrderResponseId.model_validate(
        {
            "orderId": 7,
            "cashMargin": "CASH",
            "futureOrderIdField": "preserved",
        }
    )
    assert not hasattr(preview, "futurePreviewField")
    assert "futurePreviewField" not in preview.model_dump(by_alias=True)
    assert not hasattr(order, "futureOrderIdField")
    assert "futureOrderIdField" not in order.model_dump(by_alias=True)
    assert_only_modeled_fields(preview)
    assert_only_modeled_fields(order)
