"""Typed order request and response models."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from etrade_python._dates import parse_broker_datetime

_CLIENT_ORDER_ID_RE = re.compile(r"^[A-Za-z0-9]{1,20}$")


class BrokerModel(BaseModel):
    """Base response model that discards unmodeled broker fields."""

    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)


def _strip_broker_metadata(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _strip_broker_metadata(item)
            for key, item in cast(dict[str, object], value).items()
            if key != "broker_metadata"
        }
    if isinstance(value, list):
        return [_strip_broker_metadata(item) for item in cast(list[object], value)]
    return value


def _normalize_aliases(value: object, aliases: dict[str, str]) -> object:
    if not isinstance(value, dict):
        return value
    data = dict(cast(dict[str, Any], value))
    for source, target in aliases.items():
        if source in data and target not in data:
            data[target] = data[source]
        data.pop(source, None)
    return data


def _normalize_response_ids(value: object, key: str, wrapper: str) -> object:
    if isinstance(value, BaseModel):
        value = value.model_dump(by_alias=True)
    if isinstance(value, dict):
        data = cast(dict[str, Any], value)
        if wrapper in data:
            value = data[wrapper]
        elif isinstance(data.get(key), (dict, list)):
            value = data[key]
    if value is None or value == {}:
        return []
    if isinstance(value, int):
        return [{key: value}]
    if isinstance(value, dict):
        return [cast(dict[str, Any], value)]
    if isinstance(value, list):
        items: list[object] = []
        for item in cast(list[object], value):
            if isinstance(item, int):
                items.append({key: item})
            elif isinstance(item, BaseModel):
                items.append(item.model_dump(by_alias=True))
            else:
                items.append(item)
        return items
    return value


class OrderProductId(BrokerModel):
    symbol: str | None = None
    type_code: str | None = Field(default=None, alias="typeCode")


class OrderProduct(BrokerModel):
    symbol: str | None = None
    security_type: str | None = Field(default=None, alias="securityType")
    security_sub_type: str | None = Field(default=None, alias="securitySubType")
    call_put: str | None = Field(default=None, alias="callPut")
    expiry_year: int | None = Field(default=None, alias="expiryYear")
    expiry_month: int | None = Field(default=None, alias="expiryMonth")
    expiry_day: int | None = Field(default=None, alias="expiryDay")
    strike_price: Decimal | None = Field(default=None, alias="strikePrice")
    expiry_type: str | None = Field(default=None, alias="expiryType")

    @field_validator("symbol", "security_type", "security_sub_type", "call_put", "expiry_type")
    @classmethod
    def nonempty_strings(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("A nonempty value is required")
        return value


class OrderResponseProduct(OrderProduct):
    """Product details returned by the broker, retaining request-model compatibility."""

    product_id: OrderProductId | None = Field(default=None, alias="productId")

    @model_validator(mode="before")
    @classmethod
    def normalize_product_id(cls, value: object) -> object:
        return _normalize_aliases(value, {"ProductId": "productId"})


class OrderLot(BrokerModel):
    id: int | None = None
    size: Decimal | None = None


def _empty_order_lots() -> list[OrderLot]:
    return []


class OrderLots(BrokerModel):
    lots: list[OrderLot] = Field(default_factory=_empty_order_lots, alias="lot")

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        for source in ("Lot", "lots"):
            if source in data and "lot" not in data:
                data["lot"] = data[source]
            data.pop(source, None)
        return data

    @field_validator("lots", mode="before")
    @classmethod
    def normalize_lots(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        return value


class MFQuantity(BrokerModel):
    cash: Decimal | None = None
    margin: Decimal | None = None
    cusip: str | None = None


class OrderInstrumentRequest(BaseModel):
    """Instrument request entry inside an E*TRADE order body."""

    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True)

    product: OrderProduct = Field(alias="Product")
    order_action: str = Field(alias="orderAction")
    quantity_type: str | None = Field(default="QUANTITY", alias="quantityType")
    quantity: Decimal | None = None
    ordered_quantity: Decimal | None = Field(default=None, alias="orderedQuantity")
    lots: OrderLots | None = None
    mf_quantity: MFQuantity | None = Field(default=None, alias="mfQuantity")
    osi_key: str | None = Field(default=None, alias="osiKey")
    mf_transaction: str | None = Field(default=None, alias="mfTransaction")
    reserve_order: bool | None = Field(default=None, alias="reserveOrder")
    reserve_quantity: Decimal | None = Field(default=None, alias="reserveQuantity")

    @field_validator("order_action", "quantity_type", "osi_key", "mf_transaction")
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("A nonempty value is required")
        return normalized

    @field_validator("quantity", "ordered_quantity", "reserve_quantity")
    @classmethod
    def positive_quantities(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value < 0:
            raise ValueError("Quantity values must be nonnegative")
        return value


class OrderInstrument(BrokerModel):
    product: OrderResponseProduct | None = Field(default=None, alias="Product")
    symbol_description: str | None = Field(default=None, alias="symbolDescription")
    order_action: str | None = Field(default=None, alias="orderAction")
    quantity_type: str | None = Field(default=None, alias="quantityType")
    quantity: Decimal | None = None
    cancel_quantity: Decimal | None = Field(default=None, alias="cancelQuantity")
    ordered_quantity: Decimal | None = Field(default=None, alias="orderedQuantity")
    filled_quantity: Decimal | None = Field(default=None, alias="filledQuantity")
    average_execution_price: Decimal | None = Field(default=None, alias="averageExecutionPrice")
    estimated_commission: Decimal | None = Field(default=None, alias="estimatedCommission")
    estimated_fees: Decimal | None = Field(default=None, alias="estimatedFees")
    bid: Decimal | None = None
    ask: Decimal | None = None
    last_price: Decimal | None = Field(default=None, alias="lastprice")
    currency: str | None = None
    lots: OrderLots | None = None
    mf_quantity: MFQuantity | None = Field(default=None, alias="mfQuantity")
    osi_key: str | None = Field(default=None, alias="osiKey")
    reserve_order: bool | None = Field(default=None, alias="reserveOrder")
    reserve_quantity: Decimal | None = Field(default=None, alias="reserveQuantity")
    mf_transaction: str | None = Field(default=None, alias="mfTransaction")

    @field_validator("product", mode="before")
    @classmethod
    def normalize_product_model(cls, value: object) -> object:
        if isinstance(value, OrderProduct) and not isinstance(value, OrderResponseProduct):
            return value.model_dump(by_alias=True)
        return value

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        aliases = {"product": "Product", "Lots": "lots", "MFQuantity": "mfQuantity"}
        for source, target in aliases.items():
            if source in data and target not in data:
                data[target] = data[source]
            data.pop(source, None)
        return data


class Message(BrokerModel):
    description: str | None = None
    code: int | None = None
    type: str | None = None


def _empty_messages() -> list[Message]:
    return []


class Messages(BrokerModel):
    messages: list[Message] = Field(default_factory=_empty_messages, alias="message")

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        for source in ("Message", "messages"):
            if source in data and "message" not in data:
                data["message"] = data[source]
            data.pop(source, None)
        return data

    @field_validator("messages", mode="before")
    @classmethod
    def normalize_messages(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        return value


class OrderDetailRequest(BaseModel):
    """Order detail request entry inside preview/place requests."""

    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True)

    all_or_none: bool | str | None = Field(default=None, alias="allOrNone")
    price_type: str = Field(alias="priceType")
    order_term: str = Field(alias="orderTerm")
    market_session: str | None = Field(default="REGULAR", alias="marketSession")
    stop_price: Decimal | str | None = Field(default=None, alias="stopPrice")
    limit_price: Decimal | None = Field(default=None, alias="limitPrice")
    stop_limit_price: Decimal | None = Field(default=None, alias="stopLimitPrice")
    offset_type: str | None = Field(default=None, alias="offsetType")
    offset_value: Decimal | None = Field(default=None, alias="offsetValue")
    routing_destination: str | None = Field(default=None, alias="routingDestination")
    disclosure: Disclosure | None = Field(default=None, alias="disclosure")
    instruments: list[OrderInstrumentRequest] = Field(alias="Instrument")

    @field_validator(
        "price_type", "order_term", "market_session", "offset_type", "routing_destination"
    )
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("A nonempty value is required")
        return normalized

    @field_validator("instruments", mode="before")
    @classmethod
    def normalize_instruments(cls, value: object) -> object:
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        return value

    @model_validator(mode="after")
    def validate_price_shape(self) -> OrderDetailRequest:
        if not self.instruments:
            raise ValueError("At least one instrument is required")
        if self.price_type in {
            "LIMIT",
            "NET_DEBIT",
            "NET_CREDIT",
            "LIMIT_ON_OPEN",
            "LIMIT_ON_CLOSE",
        }:
            if self.limit_price is None:
                raise ValueError("limit_price is required for limit price types")
        if self.price_type in {"STOP", "STOP_LIMIT"} and self.stop_price in (None, ""):
            raise ValueError("stop_price is required for stop price types")
        if self.price_type == "MARKET" and self.limit_price is not None:
            raise ValueError("limit_price is not valid for MARKET orders")
        return self


def _empty_order_instruments() -> list[OrderInstrument]:
    return []


class OrderDetail(BrokerModel):
    order_number: int | None = Field(default=None, alias="orderNumber")
    account_id: str | None = Field(default=None, alias="accountId")
    preview_time: datetime | None = Field(default=None, alias="previewTime")
    placed_time: datetime | None = Field(default=None, alias="placedTime")
    executed_time: datetime | None = Field(default=None, alias="executedTime")
    order_value: Decimal | None = Field(default=None, alias="orderValue")
    status: str | None = None
    order_type: str | None = Field(default=None, alias="orderType")
    order_term: str | None = Field(default=None, alias="orderTerm")
    price_type: str | None = Field(default=None, alias="priceType")
    price_value: str | None = Field(default=None, alias="priceValue")
    limit_price: Decimal | None = Field(default=None, alias="limitPrice")
    stop_price: Decimal | None = Field(default=None, alias="stopPrice")
    stop_limit_price: Decimal | None = Field(default=None, alias="stopLimitPrice")
    offset_type: str | None = Field(default=None, alias="offsetType")
    offset_value: Decimal | None = Field(default=None, alias="offsetValue")
    market_session: str | None = Field(default=None, alias="marketSession")
    all_or_none: bool | str | None = Field(default=None, alias="allOrNone")
    messages: Messages | None = None
    estimated_commission: Decimal | None = Field(default=None, alias="estimatedCommission")
    estimated_total_amount: Decimal | None = Field(default=None, alias="estimatedTotalAmount")
    net_price: Decimal | None = Field(default=None, alias="netPrice")
    net_bid: Decimal | None = Field(default=None, alias="netBid")
    net_ask: Decimal | None = Field(default=None, alias="netAsk")
    ratio: str | None = None
    eg_qual: str | None = Field(default=None, alias="egQual")
    instruments: list[OrderInstrument] = Field(
        default_factory=_empty_order_instruments, alias="Instrument"
    )
    routing_destination: str | None = Field(default=None, alias="routingDestination")
    bracketed_limit_price: Decimal | None = Field(default=None, alias="bracketedLimitPrice")
    initial_stop_price: Decimal | None = Field(default=None, alias="initialStopPrice")
    trail_price: Decimal | None = Field(default=None, alias="trailPrice")
    trigger_price: Decimal | None = Field(default=None, alias="triggerPrice")
    condition_price: Decimal | None = Field(default=None, alias="conditionPrice")
    condition_symbol: str | None = Field(default=None, alias="conditionSymbol")
    condition_type: str | None = Field(default=None, alias="conditionType")
    condition_follow_price: str | None = Field(default=None, alias="conditionFollowPrice")
    condition_security_type: str | None = Field(default=None, alias="conditionSecurityType")
    replaced_by_order_id: int | None = Field(default=None, alias="replacedByOrderId")
    replaces_order_id: int | None = Field(default=None, alias="replacesOrderId")
    preview_id: int | None = Field(default=None, alias="previewId")
    investment_amount: Decimal | None = Field(default=None, alias="investmentAmount")
    position_quantity: str | None = Field(default=None, alias="positionQuantity")
    aip_flag: bool | None = Field(default=None, alias="aipFlag")
    re_invest_option: str | None = Field(default=None, alias="reInvestOption")
    estimated_fees: Decimal | None = Field(default=None, alias="estimatedFees")
    gcd: int | None = None
    mf_price_type: str | None = Field(default=None, alias="mfpriceType")

    @field_validator("preview_time", "placed_time", "executed_time", mode="before")
    @classmethod
    def parse_times(cls, value: object) -> datetime | None:
        return parse_broker_datetime(value)

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        aliases = {"instrument": "Instrument", "messages": "messages", "Messages": "messages"}
        for source, target in aliases.items():
            if source in data and target not in data:
                data[target] = data[source]
            if source != target:
                data.pop(source, None)
        if isinstance(data.get("Instrument"), dict):
            nested = cast(dict[str, Any], data["Instrument"])
            data["Instrument"] = nested.get("Instrument", nested)
            if isinstance(data["Instrument"], dict):
                data["Instrument"] = [data["Instrument"]]
        return data

    @field_validator("instruments", mode="before")
    @classmethod
    def normalize_instruments(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            nested = cast(dict[str, Any], value)
            if "Instrument" in nested:
                return nested["Instrument"]
            return [nested]
        return value


def _empty_event_instruments() -> list[OrderInstrument]:
    return []


class OrderEvent(BrokerModel):
    name: str | None = None
    date_time: datetime | None = Field(default=None, alias="dateTime")
    order_number: int | None = Field(default=None, alias="orderNumber")
    instruments: list[OrderInstrument] = Field(
        default_factory=_empty_event_instruments, alias="instrument"
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        if isinstance(data.get("instrument"), dict):
            nested = cast(dict[str, Any], data["instrument"])
            data["instrument"] = nested.get("Instrument", nested)
            if isinstance(data["instrument"], dict):
                data["instrument"] = [data["instrument"]]
        return data

    @field_validator("date_time", mode="before")
    @classmethod
    def parse_date_time(cls, value: object) -> datetime | None:
        return parse_broker_datetime(value)

    @field_validator("instruments", mode="before")
    @classmethod
    def normalize_instruments(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            nested = cast(dict[str, Any], value)
            if "Instrument" in nested:
                return nested["Instrument"]
            return [nested]
        return value


def _empty_order_events() -> list[OrderEvent]:
    return []


class Events(BrokerModel):
    events: list[OrderEvent] = Field(default_factory=_empty_order_events, alias="event")

    @field_validator("events", mode="before")
    @classmethod
    def normalize_events(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        return value


def _empty_order_details() -> list[OrderDetail]:
    return []


class Order(BrokerModel):
    order_id: int | None = Field(default=None, alias="orderId")
    details: str | None = None
    order_type: str | None = Field(default=None, alias="orderType")
    total_order_value: Decimal | None = Field(default=None, alias="totalOrderValue")
    total_commission: Decimal | None = Field(default=None, alias="totalCommission")
    order_details: list[OrderDetail] = Field(
        default_factory=_empty_order_details, alias="orderDetail"
    )
    events: Events | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        for source in ("OrderDetail", "orderDetails"):
            if source in data and "orderDetail" not in data:
                data["orderDetail"] = data[source]
            data.pop(source, None)
        if "events" in data and isinstance(data["events"], dict) and "event" not in data["events"]:
            data["events"] = {"event": data["events"]}
        return data

    @field_validator("order_details", mode="before")
    @classmethod
    def normalize_details(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        return value


class PreviewId(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    preview_id: int = Field(alias="previewId")


class OrderId(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    order_id: int = Field(alias="orderId")


class PreviewResponseId(PreviewId, BrokerModel):
    """Preview ID and broker margin designation; placement requests use PreviewId."""

    cash_margin: str | None = Field(default=None, alias="cashMargin")


class OrderResponseId(OrderId, BrokerModel):
    """Order ID and margin designation returned by the broker."""

    cash_margin: str | None = Field(default=None, alias="cashMargin")


class OrderBuyPowerEffect(BrokerModel):
    current_bp: Decimal | None = Field(default=None, alias="currentBp")
    current_oor: Decimal | None = Field(default=None, alias="currentOor")
    current_net_bp: Decimal | None = Field(default=None, alias="currentNetBp")
    current_order_impact: Decimal | None = Field(default=None, alias="currentOrderImpact")
    net_bp: Decimal | None = Field(default=None, alias="netBp")


class CashBuyingPowerDetails(BrokerModel):
    settled: OrderBuyPowerEffect | None = None
    settled_unsettled: OrderBuyPowerEffect | None = Field(default=None, alias="settledUnsettled")

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        return _normalize_aliases(
            value, {"Settled": "settled", "SettledUnsettled": "settledUnsettled"}
        )


class MarginBuyingPowerDetails(BrokerModel):
    non_marginable: OrderBuyPowerEffect | None = Field(default=None, alias="nonMarginable")
    marginable: OrderBuyPowerEffect | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        return _normalize_aliases(
            value, {"NonMarginable": "nonMarginable", "Marginable": "marginable"}
        )


class DtBuyingPowerDetails(MarginBuyingPowerDetails):
    """Day-trading buying-power effects for marginable and non-marginable securities."""


class PortfolioMargin(BrokerModel):
    house_excess_equity_new: Decimal | None = Field(default=None, alias="houseExcessEquityNew")
    pm_eligible: bool | None = Field(default=None, alias="pmEligible")
    house_excess_equity_curr: Decimal | None = Field(default=None, alias="houseExcessEquityCurr")
    house_excess_equity_change: Decimal | None = Field(
        default=None, alias="houseExcessEquityChange"
    )


class Disclosure(BrokerModel):
    eh_disclosure_flag: bool | None = Field(default=None, alias="ehDisclosureFlag")
    ah_disclosure_flag: bool | None = Field(default=None, alias="ahDisclosureFlag")
    conditional_disclosure_flag: bool | None = Field(
        default=None, alias="conditionalDisclosureFlag"
    )
    ao_disclosure_flag: bool | None = Field(default=None, alias="aoDisclosureFlag")
    mf_fl_consent: bool | None = Field(default=None, alias="mfFLConsent")
    mf_eo_consent: bool | None = Field(default=None, alias="mfEOConsent")


class OrdersRequest(BaseModel):
    """Query parameters for listing orders."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    marker: str | None = None
    count: int | None = Field(default=None, ge=1, le=100)
    status: str | None = None
    from_date: str | None = Field(default=None, alias="fromDate")
    to_date: str | None = Field(default=None, alias="toDate")
    symbol: str | None = None
    security_type: str | None = Field(default=None, alias="securityType")
    transaction_type: str | None = Field(default=None, alias="transactionType")
    market_session: str | None = Field(default=None, alias="marketSession")

    @field_validator(
        "marker",
        "status",
        "from_date",
        "to_date",
        "symbol",
        "security_type",
        "transaction_type",
        "market_session",
    )
    @classmethod
    def normalize_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("A nonempty value is required")
        return normalized

    def query_params(self) -> dict[str, str | int | None]:
        return {
            "marker": self.marker,
            "count": self.count,
            "status": self.status,
            "fromDate": self.from_date,
            "toDate": self.to_date,
            "symbol": self.symbol,
            "securityType": self.security_type,
            "transactionType": self.transaction_type,
            "marketSession": self.market_session,
        }


class PreviewOrderRequest(BaseModel):
    """Request body for previewing a new or changed order."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    order_type: str = Field(alias="orderType")
    client_order_id: str = Field(alias="clientOrderId")
    orders: list[OrderDetailRequest] = Field(alias="Order")

    @field_validator("order_type")
    @classmethod
    def normalize_order_type(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A nonempty value is required")
        return value.strip().upper()

    @field_validator("client_order_id")
    @classmethod
    def valid_client_order_id(cls, value: str) -> str:
        normalized = value.strip()
        if not _CLIENT_ORDER_ID_RE.fullmatch(normalized):
            raise ValueError("client_order_id must be 1-20 alphanumeric characters")
        return normalized

    @field_validator("orders", mode="before")
    @classmethod
    def normalize_orders(cls, value: object) -> object:
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        return value

    @model_validator(mode="after")
    def validate_orders(self) -> PreviewOrderRequest:
        if not self.orders:
            raise ValueError("At least one order is required")
        return self

    def request_body(self) -> dict[str, Any]:
        payload = self.model_dump(by_alias=True, exclude_none=True, mode="json")
        return {"PreviewOrderRequest": cast(dict[str, Any], _strip_broker_metadata(payload))}


class PlaceOrderRequest(PreviewOrderRequest):
    """Request body for placing a previewed new or changed order."""

    preview_ids: list[PreviewId] = Field(alias="PreviewIds")

    @field_validator("preview_ids", mode="before")
    @classmethod
    def normalize_preview_ids(cls, value: object) -> object:
        if value is None:
            return value
        if isinstance(value, int):
            return [{"previewId": value}]
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        if isinstance(value, list):
            items = cast(list[object], value)
            return [{"previewId": item} if isinstance(item, int) else item for item in items]
        return value

    @model_validator(mode="after")
    def validate_preview_ids(self) -> PlaceOrderRequest:
        if not self.preview_ids:
            raise ValueError("At least one preview ID is required")
        return self

    def request_body(self) -> dict[str, Any]:
        payload = self.model_dump(by_alias=True, exclude_none=True, mode="json")
        return {"PlaceOrderRequest": cast(dict[str, Any], _strip_broker_metadata(payload))}


class CancelOrderRequest(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    order_id: int = Field(alias="orderId", ge=1)

    def request_body(self) -> dict[str, Any]:
        return {"CancelOrderRequest": self.model_dump(by_alias=True, mode="json")}


def _empty_orders() -> list[Order]:
    return []


class OrdersResponse(BrokerModel):
    orders: list[Order] = Field(default_factory=_empty_orders, alias="order")
    marker: str | None = None
    next: str | None = None
    messages: Messages | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        for source in ("Order", "orders"):
            if source in data and "order" not in data:
                data["order"] = data[source]
            data.pop(source, None)
        for source in ("Messages",):
            if source in data and "messages" not in data:
                data["messages"] = data[source]
            data.pop(source, None)
        return data

    @field_validator("orders", mode="before")
    @classmethod
    def normalize_orders(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        return value


def _empty_response_order_details() -> list[OrderDetail]:
    return []


def _empty_preview_ids() -> list[PreviewResponseId]:
    return []


class PreviewOrderResponse(BrokerModel):
    order_type: str | None = Field(default=None, alias="orderType")
    total_order_value: Decimal | None = Field(default=None, alias="totalOrderValue")
    preview_time: datetime | None = Field(default=None, alias="previewTime")
    dst_flag: bool | None = Field(default=None, alias="dstFlag")
    account_id: str | None = Field(default=None, alias="accountId")
    option_level_cd: int | None = Field(default=None, alias="optionLevelCd")
    margin_level_cd: str | None = Field(default=None, alias="marginLevelCd")
    orders: list[OrderDetail] = Field(default_factory=_empty_response_order_details, alias="Order")
    preview_ids: list[PreviewResponseId] = Field(
        default_factory=_empty_preview_ids, alias="PreviewIds"
    )
    disclosure: Disclosure | None = Field(default=None, alias="Disclosure")
    settled: OrderBuyPowerEffect | None = None
    settled_unsettled: OrderBuyPowerEffect | None = Field(default=None, alias="settledUnsettled")
    message_list: Messages | None = Field(default=None, alias="messageList")
    total_commission: Decimal | None = Field(default=None, alias="totalCommission")
    portfolio_margin: PortfolioMargin | None = Field(default=None, alias="portfolioMargin")
    is_employee: bool | None = Field(default=None, alias="isEmployee")
    commission_message: str | None = Field(default=None, alias="commissionMessage")
    client_order_id: str | None = Field(default=None, alias="clientOrderId")
    margin_bp_details: MarginBuyingPowerDetails | None = Field(
        default=None, alias="marginBpDetails"
    )
    cash_bp_details: CashBuyingPowerDetails | None = Field(default=None, alias="cashBpDetails")
    dt_bp_details: DtBuyingPowerDetails | None = Field(default=None, alias="dtBpDetails")

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        return _normalize_aliases(
            value,
            {
                "order": "Order",
                "previewIds": "PreviewIds",
                "disclosure": "Disclosure",
                "MessageList": "messageList",
                "Messages": "messageList",
                "messages": "messageList",
                "PortfolioMargin": "portfolioMargin",
                "MarginBpDetails": "marginBpDetails",
                "CashBpDetails": "cashBpDetails",
                "DtBpDetails": "dtBpDetails",
            },
        )

    @field_validator("preview_time", mode="before")
    @classmethod
    def parse_preview_time(cls, value: object) -> datetime | None:
        return parse_broker_datetime(value)

    @field_validator("preview_ids", mode="before")
    @classmethod
    def normalize_preview_ids(cls, value: object) -> object:
        return _normalize_response_ids(value, "previewId", "PreviewId")

    @field_validator("orders", mode="before")
    @classmethod
    def normalize_lists(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        return value


def _empty_order_ids() -> list[OrderResponseId]:
    return []


class PlaceOrderResponse(BrokerModel):
    order_type: str | None = Field(default=None, alias="orderType")
    placed_time: datetime | None = Field(default=None, alias="placedTime")
    dst_flag: bool | None = Field(default=None, alias="dstFlag")
    account_id: str | None = Field(default=None, alias="accountId")
    option_level_cd: int | None = Field(default=None, alias="optionLevelCd")
    margin_level_cd: str | None = Field(default=None, alias="marginLevelCd")
    orders: list[OrderDetail] = Field(default_factory=_empty_response_order_details, alias="Order")
    order_ids: list[OrderResponseId] = Field(default_factory=_empty_order_ids, alias="OrderIds")
    message_list: Messages | None = Field(default=None, alias="messageList")
    total_order_value: Decimal | None = Field(default=None, alias="totalOrderValue")
    total_commission: Decimal | None = Field(default=None, alias="totalCommission")
    order_id: int | None = Field(default=None, alias="orderId")
    is_employee: bool | None = Field(default=None, alias="isEmployee")
    commission_msg: str | None = Field(default=None, alias="commissionMsg")
    portfolio_margin: PortfolioMargin | None = Field(default=None, alias="portfolioMargin")
    disclosure: Disclosure | None = None
    client_order_id: str | None = Field(default=None, alias="clientOrderId")

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        return _normalize_aliases(
            value,
            {
                "order": "Order",
                "orderIds": "OrderIds",
                "Disclosure": "disclosure",
                "MessageList": "messageList",
                "Messages": "messageList",
                "messages": "messageList",
                "PortfolioMargin": "portfolioMargin",
            },
        )

    @field_validator("placed_time", mode="before")
    @classmethod
    def parse_placed_time(cls, value: object) -> datetime | None:
        return parse_broker_datetime(value)

    @field_validator("order_ids", mode="before")
    @classmethod
    def normalize_order_ids(cls, value: object) -> object:
        return _normalize_response_ids(value, "orderId", "OrderId")

    @field_validator("orders", mode="before")
    @classmethod
    def normalize_lists(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        return value


class CancelOrderResponse(BrokerModel):
    account_id: str | None = Field(default=None, alias="accountId")
    order_id: int | None = Field(default=None, alias="orderId")
    cancel_time: datetime | None = Field(default=None, alias="cancelTime")
    messages: Messages | None = None

    @field_validator("cancel_time", mode="before")
    @classmethod
    def parse_cancel_time(cls, value: object) -> datetime | None:
        return parse_broker_datetime(value)

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        if "Messages" in data and "messages" not in data:
            data["messages"] = data["Messages"]
        data.pop("Messages", None)
        return data
