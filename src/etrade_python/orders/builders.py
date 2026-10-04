"""Fluent helpers for constructing E*TRADE order requests."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import TypeAlias, cast

from etrade_python.orders.models import (
    OrderDetailRequest,
    OrderInstrumentRequest,
    OrderProduct,
    PlaceOrderRequest,
    PreviewId,
    PreviewOrderRequest,
)

NumberLike: TypeAlias = Decimal | int | str | float
PreviewIdInput: TypeAlias = int | dict[str, int]


class OrderBuilder:
    """Build typed E*TRADE preview and place order requests.

    The builder stores account and order metadata for CLI/demo workflows, but the
    E*TRADE request body itself is still represented by the lower-level Pydantic
    request models used by :class:`etrade_python.orders.service.OrdersService`.
    """

    def __init__(self, account_id_key: str) -> None:
        self._account_id_key = _nonempty(account_id_key, "account_id_key")
        self._order_id: int | None = None
        self._order_type: str | None = None
        self._client_order_id: str | None = None
        self._symbol: str | None = None
        self._expiration: date | None = None
        self._quantity_type = "QUANTITY"
        self._order_term = "GOOD_FOR_DAY"
        self._price_type: str | None = None
        self._limit_price: Decimal | None = None
        self._stop_price: Decimal | str | None = None
        self._stop_limit_price: Decimal | None = None
        self._market_session = "REGULAR"
        self._all_or_none: bool | str | None = "false"
        self._instruments: list[OrderInstrumentRequest] = []

    @classmethod
    def for_account(cls, account_id_key: str) -> OrderBuilder:
        return cls(account_id_key)

    @property
    def account_id_key(self) -> str:
        return self._account_id_key

    @property
    def order_id(self) -> int | None:
        return self._order_id

    def client_order_id(self, client_order_id: str) -> OrderBuilder:
        self._client_order_id = _nonempty(client_order_id, "client_order_id")
        return self

    def order_id_for_change(self, order_id: int) -> OrderBuilder:
        if isinstance(order_id, bool) or order_id < 1:
            raise ValueError("order_id must be a positive integer")
        self._order_id = order_id
        return self

    def order_type(self, order_type: str) -> OrderBuilder:
        self._order_type = _upper(order_type, "order_type")
        return self

    def with_symbol(self, symbol: str) -> OrderBuilder:
        self._symbol = _upper(symbol, "symbol")
        return self

    def with_expiration(self, expiration: date) -> OrderBuilder:
        self._expiration = expiration
        return self

    def quantity_type(self, quantity_type: str) -> OrderBuilder:
        self._quantity_type = _upper(quantity_type, "quantity_type")
        return self

    def term(self, order_term: str) -> OrderBuilder:
        self._order_term = _upper(order_term, "order_term")
        return self

    def gfd(self) -> OrderBuilder:
        return self.term("GOOD_FOR_DAY")

    def gtc(self) -> OrderBuilder:
        return self.term("GOOD_UNTIL_CANCEL")

    def price_type(self, price_type: str) -> OrderBuilder:
        self._price_type = _upper(price_type, "price_type")
        return self

    def market(self) -> OrderBuilder:
        self._price_type = "MARKET"
        self._limit_price = None
        self._stop_price = None
        self._stop_limit_price = None
        return self

    def limit(self, limit_price: NumberLike) -> OrderBuilder:
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

    def market_session(self, market_session: str) -> OrderBuilder:
        self._market_session = _upper(market_session, "market_session")
        return self

    def all_or_none(self, all_or_none: bool) -> OrderBuilder:
        self._all_or_none = all_or_none
        return self

    def add_equity(
        self,
        order_action: str,
        quantity: NumberLike,
        *,
        symbol: str | None = None,
    ) -> OrderBuilder:
        symbol = _upper(symbol, "symbol") if symbol is not None else self._require_symbol()
        self._instruments.append(
            OrderInstrumentRequest(
                Product=OrderProduct(symbol=symbol, securityType="EQ"),
                orderAction=order_action,
                quantityType=self._quantity_type,
                quantity=_positive_decimal(quantity, "quantity"),
            )
        )
        return self

    def add_long_call(
        self, strike_price: NumberLike, quantity: NumberLike = Decimal("1")
    ) -> OrderBuilder:
        return self._add_option_leg("CALL", "BUY_OPEN", strike_price, quantity)

    def add_short_call(
        self, strike_price: NumberLike, quantity: NumberLike = Decimal("1")
    ) -> OrderBuilder:
        return self._add_option_leg("CALL", "SELL_OPEN", strike_price, quantity)

    def add_long_put(
        self, strike_price: NumberLike, quantity: NumberLike = Decimal("1")
    ) -> OrderBuilder:
        return self._add_option_leg("PUT", "BUY_OPEN", strike_price, quantity)

    def add_short_put(
        self, strike_price: NumberLike, quantity: NumberLike = Decimal("1")
    ) -> OrderBuilder:
        return self._add_option_leg("PUT", "SELL_OPEN", strike_price, quantity)

    def equity_limit(
        self,
        symbol: str,
        *,
        action: str,
        quantity: NumberLike,
        limit_price: NumberLike,
    ) -> OrderBuilder:
        return (
            self.order_type("EQ")
            .with_symbol(symbol)
            .limit(limit_price)
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
            .limit(limit_price)
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
        return PreviewOrderRequest(
            orderType=cast(str, self._order_type),
            clientOrderId=cast(str, self._client_order_id),
            Order=[self._build_order_detail()],
        )

    def build_change_preview_request(self, order_id: int | None = None) -> PreviewOrderRequest:
        if order_id is not None:
            self.order_id_for_change(order_id)
        if self._order_id is None:
            raise ValueError("order_id is required to preview an order change")
        return self.build_preview_request()

    def build_place_request(self, preview_ids: Sequence[PreviewIdInput | int]) -> PlaceOrderRequest:
        self._assert_ready_for_preview()
        normalized_ids = _normalize_preview_ids(preview_ids)
        return PlaceOrderRequest(
            orderType=cast(str, self._order_type),
            clientOrderId=cast(str, self._client_order_id),
            PreviewIds=normalized_ids,
            Order=[self._build_order_detail()],
        )

    def build_change_place_request(
        self, preview_ids: Sequence[PreviewIdInput | int], order_id: int | None = None
    ) -> PlaceOrderRequest:
        if order_id is not None:
            self.order_id_for_change(order_id)
        if self._order_id is None:
            raise ValueError("order_id is required to place an order change")
        return self.build_place_request(preview_ids)

    def _add_option_leg(
        self, call_put: str, order_action: str, strike_price: NumberLike, quantity: NumberLike
    ) -> OrderBuilder:
        expiration = self._require_expiration()
        self._instruments.append(
            OrderInstrumentRequest(
                Product=OrderProduct(
                    symbol=self._require_symbol(),
                    securityType="OPTN",
                    callPut=call_put,
                    expiryYear=expiration.year,
                    expiryMonth=expiration.month,
                    expiryDay=expiration.day,
                    strikePrice=_positive_decimal(strike_price, "strike_price"),
                ),
                orderAction=order_action,
                quantityType=self._quantity_type,
                quantity=_positive_decimal(quantity, "quantity"),
            )
        )
        return self

    def _build_order_detail(self) -> OrderDetailRequest:
        return OrderDetailRequest(
            allOrNone=self._all_or_none,
            priceType=cast(str, self._price_type),
            orderTerm=self._order_term,
            marketSession=self._market_session,
            stopPrice=self._stop_price,
            limitPrice=self._limit_price,
            stopLimitPrice=self._stop_limit_price,
            Instrument=list(self._instruments),
        )

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

    def _require_expiration(self) -> date:
        if self._expiration is None:
            raise ValueError("expiration is required for option legs")
        return self._expiration


def _normalize_preview_ids(preview_ids: Sequence[PreviewIdInput | int]) -> list[PreviewId]:
    if not preview_ids:
        raise ValueError("At least one preview ID is required")
    normalized: list[PreviewId] = []
    for preview_id in preview_ids:
        if isinstance(preview_id, bool):
            raise ValueError("preview IDs must be positive integers")
        if isinstance(preview_id, int):
            if preview_id < 1:
                raise ValueError("preview IDs must be positive integers")
            normalized.append(PreviewId(previewId=preview_id))
            continue
        value = preview_id.get("previewId")
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("preview IDs must be positive integers")
        normalized.append(PreviewId(previewId=value))
    return normalized


def _decimal(value: NumberLike, label: str) -> Decimal:
    try:
        decimal = Decimal(str(value))
    except Exception as exc:  # noqa: BLE001 - convert arbitrary construction failures
        raise ValueError(f"{label} must be a decimal value") from exc
    if not decimal.is_finite():
        raise ValueError(f"{label} must be finite")
    return decimal


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
