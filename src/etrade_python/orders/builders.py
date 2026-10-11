"""Fluent helpers for constructing E*TRADE order requests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any, Literal, TypeAlias, cast

from etrade_python.orders.models import (
    Disclosure,
    OrderInstrumentRequest,
    PlaceOrderRequest,
    PreviewId,
    PreviewOrderRequest,
)
from etrade_python.orders.values import (
    VALID_MARKET_SESSIONS,
    VALID_ORDER_ACTIONS,
    VALID_ORDER_TERMS,
    VALID_ORDER_TYPES,
    VALID_PRICE_TYPES,
    VALID_QUANTITY_TYPES,
    VALID_SECURITY_TYPES,
    MarketSession,
    OrderAction,
    OrderTerm,
    OrderType,
    PriceType,
    QuantityType,
    SecurityType,
)

__all__ = [
    "QuantityType",
    "OrderTerm",
    "OrderType",
    "PriceType",
    "MarketSession",
    "OrderAction",
    "SecurityType",
    "VALID_QUANTITY_TYPES",
    "VALID_ORDER_TERMS",
    "VALID_ORDER_TYPES",
    "VALID_PRICE_TYPES",
    "VALID_MARKET_SESSIONS",
    "VALID_ORDER_ACTIONS",
    "VALID_SECURITY_TYPES",
    "OrderBuilder",
    "NumberLike",
    "PreviewIdInput",
    "InstrumentInput",
    "DisclosureInput",
]


NumberLike: TypeAlias = Decimal | int | str | float
PreviewIdInput: TypeAlias = int | dict[str, int] | PreviewId
InstrumentInput: TypeAlias = OrderInstrumentRequest | Mapping[str, Any]
DisclosureInput: TypeAlias = Disclosure | Mapping[str, Any]


class OrderBuilder:
    """Build typed E*TRADE preview and place order requests."""

    def __init__(self, account_id_key: str) -> None:
        self._account_id_key = _nonempty(account_id_key, "account_id_key")
        self._order_id: int | None = None
        self._order_type: OrderType | None = None
        self._client_order_id: str | None = None
        self._symbol: str | None = None
        self._expiration: date | None = None
        self._quantity_type: QuantityType | None = None
        self._order_term: OrderTerm = "GOOD_FOR_DAY"
        self._price_type: PriceType | None = None
        self._limit_price: Decimal | None = None
        self._stop_price: Decimal | str | None = None
        self._stop_limit_price: Decimal | None = None
        self._market_session: MarketSession = "REGULAR"
        self._all_or_none: bool | str | None = "false"
        self._disclosure: Disclosure | None = None
        self._detail_fields: dict[str, Any] = {}
        self._instruments: list[OrderInstrumentRequest] = []

    @classmethod
    def for_account(cls, account_id_key: str) -> OrderBuilder:
        return cls(account_id_key)

    @property
    def account_id_key(self) -> str:
        return self._account_id_key

    @property
    def order_id_value(self) -> int | None:
        return self._order_id

    @property
    def order_id_for_change_value(self) -> int | None:
        return self._order_id

    def client_order_id(self, client_order_id: str) -> OrderBuilder:
        self._client_order_id = _nonempty(client_order_id, "client_order_id")
        return self

    def order_id(self, order_id: int) -> OrderBuilder:
        if type(order_id) is not int or order_id < 1:
            raise ValueError("order_id must be a positive integer")
        self._order_id = order_id
        return self

    def order_id_for_change(self, order_id: int) -> OrderBuilder:
        return self.order_id(order_id)

    def order_type(self, order_type: OrderType | str) -> OrderBuilder:
        self._order_type = cast(OrderType, _valid_enum(order_type, VALID_ORDER_TYPES, "order_type"))
        return self

    def with_symbol(self, symbol: str) -> OrderBuilder:
        self._symbol = _upper(symbol, "symbol")
        return self

    def with_expiry(self, year: int, month: int, day: int) -> OrderBuilder:
        try:
            self._expiration = date(year, month, day)
        except ValueError as exc:
            raise ValueError("expiry date must be a valid calendar date") from exc
        return self

    def with_expiration(self, expiration: date) -> OrderBuilder:
        self._expiration = expiration
        return self

    def quantity_type(self, quantity_type: QuantityType | str) -> OrderBuilder:
        self._quantity_type = cast(
            QuantityType, _valid_enum(quantity_type, VALID_QUANTITY_TYPES, "quantity_type")
        )
        return self

    def term(self, order_term: OrderTerm | str) -> OrderBuilder:
        self._order_term = cast(OrderTerm, _valid_enum(order_term, VALID_ORDER_TERMS, "order_term"))
        return self

    def gfd(self) -> OrderBuilder:
        return self.term("GOOD_FOR_DAY")

    def gtc(self) -> OrderBuilder:
        return self.term("GOOD_UNTIL_CANCEL")

    def price_type(self, price_type: PriceType | str) -> OrderBuilder:
        self._price_type = cast(PriceType, _valid_enum(price_type, VALID_PRICE_TYPES, "price_type"))
        return self

    def market(self) -> OrderBuilder:
        self._price_type = "MARKET"
        self._limit_price = None
        self._stop_price = None
        self._stop_limit_price = None
        return self

    def limit(self, limit_price: NumberLike) -> OrderBuilder:
        return self.limit_price(limit_price)

    def limit_price(self, limit_price: NumberLike) -> OrderBuilder:
        self._price_type = "LIMIT"
        self._limit_price = _positive_decimal(limit_price, "limit_price")
        return self

    def net_debit(self, limit_price: NumberLike) -> OrderBuilder:
        self._price_type = "NET_DEBIT"
        self._limit_price = _positive_decimal(limit_price, "limit_price")
        return self

    def net_credit(self, limit_price: NumberLike) -> OrderBuilder:
        self._price_type = "NET_CREDIT"
        self._limit_price = _positive_decimal(limit_price, "limit_price")
        return self

    def stop(self, stop_price: NumberLike) -> OrderBuilder:
        return self.stop_price(stop_price)

    def stop_price(self, stop_price: NumberLike) -> OrderBuilder:
        self._price_type = "STOP"
        self._stop_price = _positive_decimal(stop_price, "stop_price")
        self._limit_price = None
        return self

    def stop_limit(self, stop_price: NumberLike, limit_price: NumberLike) -> OrderBuilder:
        self._price_type = "STOP_LIMIT"
        self._stop_price = _positive_decimal(stop_price, "stop_price")
        self._stop_limit_price = _positive_decimal(limit_price, "stop_limit_price")
        self._limit_price = self._stop_limit_price
        return self

    def stop_limit_price(self, stop_limit_price: NumberLike) -> OrderBuilder:
        self._price_type = "STOP_LIMIT"
        self._stop_limit_price = _positive_decimal(stop_limit_price, "stop_limit_price")
        self._limit_price = self._stop_limit_price
        return self

    def market_session(self, market_session: MarketSession | str) -> OrderBuilder:
        self._market_session = cast(
            MarketSession, _valid_enum(market_session, VALID_MARKET_SESSIONS, "market_session")
        )
        return self

    def all_or_none(self, all_or_none: bool) -> OrderBuilder:
        self._all_or_none = all_or_none
        return self

    def disclosure(self, disclosure: DisclosureInput) -> OrderBuilder:
        if isinstance(disclosure, Disclosure):
            self._disclosure = disclosure
        else:
            self._disclosure = Disclosure.model_validate(dict(disclosure))
        return self

    def with_detail(self, fields: Mapping[str, Any]) -> OrderBuilder:
        for key, value in fields.items():
            if key not in {"instrument", "Instrument"}:
                self._detail_fields[key] = value
        return self

    def add_instrument(self, instrument: InstrumentInput) -> OrderBuilder:
        if isinstance(instrument, OrderInstrumentRequest):
            model = instrument
        else:
            data = dict(instrument)
            if data.get("quantityType") is None and data.get("quantity_type") is None:
                data["quantityType"] = self._quantity_type
            elif data.get("quantityType") is not None:
                data["quantityType"] = _valid_enum(
                    str(data["quantityType"]), VALID_QUANTITY_TYPES, "quantity_type"
                )
            elif data.get("quantity_type") is not None:
                data["quantity_type"] = _valid_enum(
                    str(data["quantity_type"]), VALID_QUANTITY_TYPES, "quantity_type"
                )
            model = OrderInstrumentRequest.model_validate(data)
        self._instruments.append(model)
        return self

    def add_equity(
        self,
        order_action: OrderAction | str,
        quantity: NumberLike = Decimal("1"),
        *,
        symbol: str | None = None,
        overrides: Mapping[str, Any] | None = None,
    ) -> OrderBuilder:
        overrides = dict(overrides or {})
        action = cast(OrderAction, _valid_enum(order_action, VALID_ORDER_ACTIONS, "order_action"))
        symbol_value = _symbol_from_override(overrides, symbol, self._symbol, "equity")
        security_type = cast(
            SecurityType,
            _valid_enum(
                str(overrides.get("securityType", "EQ")), VALID_SECURITY_TYPES, "security_type"
            ),
        )
        data: dict[str, Any] = {
            "orderAction": action,
            "quantityType": overrides.get("quantityType", self._quantity_type),
            "quantity": _positive_decimal(quantity, "quantity"),
            "orderedQuantity": _optional_decimal(
                overrides.get("orderedQuantity"), "ordered_quantity"
            ),
            "Product": {"symbol": symbol_value, "securityType": security_type},
        }
        return self.add_instrument(_drop_none(data))

    def add_long_call(
        self,
        strike_price: NumberLike,
        quantity: NumberLike = Decimal("1"),
        overrides: Mapping[str, Any] | None = None,
    ) -> OrderBuilder:
        return self._add_option_leg("CALL", "BUY_OPEN", strike_price, quantity, overrides)

    def add_short_call(
        self,
        strike_price: NumberLike,
        quantity: NumberLike = Decimal("1"),
        overrides: Mapping[str, Any] | None = None,
    ) -> OrderBuilder:
        return self._add_option_leg("CALL", "SELL_OPEN", strike_price, quantity, overrides)

    def add_long_put(
        self,
        strike_price: NumberLike,
        quantity: NumberLike = Decimal("1"),
        overrides: Mapping[str, Any] | None = None,
    ) -> OrderBuilder:
        return self._add_option_leg("PUT", "BUY_OPEN", strike_price, quantity, overrides)

    def add_short_put(
        self,
        strike_price: NumberLike,
        quantity: NumberLike = Decimal("1"),
        overrides: Mapping[str, Any] | None = None,
    ) -> OrderBuilder:
        return self._add_option_leg("PUT", "SELL_OPEN", strike_price, quantity, overrides)

    def equity_limit(
        self,
        symbol: str,
        *,
        action: OrderAction | str,
        quantity: NumberLike,
        limit_price: NumberLike,
    ) -> OrderBuilder:
        return (
            self.order_type("EQ")
            .with_symbol(symbol)
            .limit_price(limit_price)
            .add_equity(action, quantity)
        )

    def long_call_limit(
        self,
        symbol: str,
        *,
        expiration: date,
        strike_price: NumberLike,
        quantity: NumberLike,
        limit_price: NumberLike,
    ) -> OrderBuilder:
        return (
            self.order_type("OPTN")
            .with_symbol(symbol)
            .with_expiration(expiration)
            .limit_price(limit_price)
            .add_long_call(strike_price, quantity)
        )

    def option_vertical_call(
        self,
        symbol: str,
        *,
        expiration: date,
        quantity: NumberLike,
        long_strike: NumberLike,
        short_strike: NumberLike,
        net_debit: NumberLike,
    ) -> OrderBuilder:
        return (
            self.order_type("SPREADS")
            .with_symbol(symbol)
            .with_expiration(expiration)
            .net_debit(net_debit)
            .add_long_call(long_strike, quantity)
            .add_short_call(short_strike, quantity)
        )

    def three_leg_call_spread_short_put(
        self,
        symbol: str,
        *,
        expiration: date,
        quantity: NumberLike,
        long_call_strike: NumberLike,
        short_call_strike: NumberLike,
        short_put_strike: NumberLike,
        net_debit: NumberLike,
    ) -> OrderBuilder:
        return (
            self.order_type("SPREADS")
            .with_symbol(symbol)
            .with_expiration(expiration)
            .net_debit(net_debit)
            .add_long_call(long_call_strike, quantity)
            .add_short_call(short_call_strike, quantity)
            .add_short_put(short_put_strike, quantity)
        )

    def iron_condor(
        self,
        symbol: str,
        *,
        expiration: date,
        quantity: NumberLike,
        short_put_strike: NumberLike,
        long_put_strike: NumberLike,
        short_call_strike: NumberLike,
        long_call_strike: NumberLike,
        net_credit: NumberLike,
    ) -> OrderBuilder:
        return (
            self.order_type("SPREADS")
            .with_symbol(symbol)
            .with_expiration(expiration)
            .net_credit(net_credit)
            .add_short_put(short_put_strike, quantity)
            .add_long_put(long_put_strike, quantity)
            .add_short_call(short_call_strike, quantity)
            .add_long_call(long_call_strike, quantity)
        )

    def buy_write(
        self,
        symbol: str,
        *,
        expiration: date,
        stock_quantity: NumberLike,
        call_quantity: NumberLike,
        call_strike: NumberLike,
        net_debit: NumberLike,
    ) -> OrderBuilder:
        return (
            self.order_type("BUY_WRITES")
            .with_symbol(symbol)
            .net_debit(net_debit)
            .add_equity("BUY", stock_quantity)
            .with_expiration(expiration)
            .add_short_call(call_strike, call_quantity)
        )

    def build_preview_request(self) -> PreviewOrderRequest:
        self._assert_ready_for_preview()
        return PreviewOrderRequest.model_validate(
            {
                "orderType": self._order_type,
                "clientOrderId": self._client_order_id,
                "Order": [self._build_order_detail_payload()],
            }
        )

    def build_change_preview_request(self, order_id: int | None = None) -> PreviewOrderRequest:
        if order_id is not None:
            self.order_id(order_id)
        if self._order_id is None:
            raise ValueError("order_id is required to preview an order change")
        return self.build_preview_request()

    def build_place_request(self, preview_ids: Sequence[PreviewIdInput]) -> PlaceOrderRequest:
        self._assert_ready_for_preview()
        normalized_ids = _normalize_preview_ids(preview_ids)
        return PlaceOrderRequest.model_validate(
            {
                "orderType": self._order_type,
                "clientOrderId": self._client_order_id,
                "PreviewIds": normalized_ids,
                "Order": [self._build_order_detail_payload()],
            }
        )

    def build_change_place_request(
        self, preview_ids: Sequence[PreviewIdInput], order_id: int | None = None
    ) -> PlaceOrderRequest:
        if order_id is not None:
            self.order_id(order_id)
        if self._order_id is None:
            raise ValueError("order_id is required to place an order change")
        return self.build_place_request(preview_ids)

    def _add_option_leg(
        self,
        call_put: Literal["CALL", "PUT"],
        order_action: OrderAction,
        strike_price: NumberLike,
        quantity: NumberLike,
        overrides: Mapping[str, Any] | None,
    ) -> OrderBuilder:
        overrides = dict(overrides or {})
        symbol = _symbol_from_override(overrides, None, self._symbol, "option")
        expiry = _expiry_from_override(overrides, self._expiration)
        security_type = cast(
            SecurityType,
            _valid_enum(
                str(overrides.get("securityType", "OPTN")), VALID_SECURITY_TYPES, "security_type"
            ),
        )
        data: dict[str, Any] = {
            "orderAction": order_action,
            "quantityType": overrides.get("quantityType", self._quantity_type),
            "quantity": _positive_decimal(quantity, "quantity"),
            "orderedQuantity": _optional_decimal(
                overrides.get("orderedQuantity", quantity), "ordered_quantity"
            ),
            "Product": {
                "symbol": symbol,
                "securityType": security_type,
                "callPut": call_put,
                "expiryYear": expiry.year,
                "expiryMonth": expiry.month,
                "expiryDay": expiry.day,
                "strikePrice": _positive_decimal(strike_price, "strike_price"),
            },
        }
        return self.add_instrument(_drop_none(data))

    def _build_order_detail_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "allOrNone": self._all_or_none,
            "priceType": self._price_type,
            "orderTerm": self._order_term,
            "marketSession": self._market_session,
            "stopPrice": self._stop_price,
            "limitPrice": self._limit_price,
            "stopLimitPrice": self._stop_limit_price,
            "disclosure": self._disclosure,
        }
        payload.update(self._detail_fields)
        payload.pop("instrument", None)
        payload.pop("Instrument", None)
        payload["Instrument"] = list(self._instruments)
        if payload.get("stopPrice") == "":
            payload["stopPrice"] = None
        return _drop_none(payload)

    def _assert_ready_for_preview(self) -> None:
        if self._client_order_id is None:
            raise ValueError("client_order_id is required")
        if self._order_type is None:
            raise ValueError("order_type is required")
        if self._price_type is None:
            raise ValueError("price_type is required")
        if not self._instruments:
            raise ValueError("At least one instrument is required")

    def _require_symbol(self) -> str:
        if self._symbol is None:
            raise ValueError("symbol is required")
        return self._symbol


def _normalize_preview_ids(preview_ids: Sequence[PreviewIdInput]) -> list[PreviewId]:
    if not preview_ids:
        raise ValueError("At least one preview ID is required")
    normalized: list[PreviewId] = []
    for preview_id in preview_ids:
        if isinstance(preview_id, PreviewId):
            PreviewId.model_validate({"previewId": preview_id.preview_id})
            normalized.append(preview_id)
            continue
        if isinstance(preview_id, bool):
            raise ValueError("preview IDs must be positive integers")
        if isinstance(preview_id, int):
            if preview_id < 1:
                raise ValueError("preview IDs must be positive integers")
            normalized.append(PreviewId(previewId=preview_id))
            continue
        if not isinstance(cast(object, preview_id), Mapping):
            raise ValueError("preview IDs must be positive integers")
        value = preview_id.get("previewId")
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("preview IDs must be positive integers")
        normalized.append(PreviewId(previewId=value))
    return normalized


def _symbol_from_override(
    overrides: Mapping[str, Any], symbol: str | None, default_symbol: str | None, leg_type: str
) -> str:
    raw_symbol = overrides.get("symbol", symbol if symbol is not None else default_symbol)
    if raw_symbol is None:
        raise ValueError(f"symbol is required for {leg_type} legs")
    return _upper(str(raw_symbol), "symbol")


def _expiry_from_override(overrides: Mapping[str, Any], default_expiration: date | None) -> date:
    if all(key in overrides for key in ("expiryYear", "expiryMonth", "expiryDay")):
        try:
            return date(
                int(overrides["expiryYear"]),
                int(overrides["expiryMonth"]),
                int(overrides["expiryDay"]),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("expiry date must be a valid calendar date") from exc
    if default_expiration is None:
        raise ValueError("expiration is required for option legs")
    return default_expiration


def _valid_enum(value: str, allowed: frozenset[str], label: str) -> str:
    normalized = _upper(value, label)
    if normalized not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ValueError(f"{label} must be one of: {allowed_values}")
    return normalized


def _decimal(value: NumberLike, label: str) -> Decimal:
    try:
        decimal = Decimal(str(value))
    except Exception as exc:  # noqa: BLE001 - convert arbitrary construction failures
        raise ValueError(f"{label} must be a decimal value") from exc
    if not decimal.is_finite():
        raise ValueError(f"{label} must be finite")
    return decimal


def _optional_decimal(value: object, label: str) -> Decimal | None:
    if value is None:
        return None
    return _decimal(cast(NumberLike, value), label)


def _positive_decimal(value: NumberLike, label: str) -> Decimal:
    decimal = _decimal(value, label)
    if decimal <= 0:
        raise ValueError(f"{label} must be positive")
    return decimal


def _nonempty(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _upper(value: str, label: str) -> str:
    return _nonempty(value, label).upper()


def _drop_none(data: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}
