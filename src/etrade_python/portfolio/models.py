"""Typed portfolio request and response models."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from etrade_python._dates import parse_broker_date, parse_broker_datetime


class BrokerModel(BaseModel):
    """Base model that preserves unmodeled broker fields."""

    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True)

    broker_metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        extra = cast(dict[str, Any], getattr(self, "__pydantic_extra__", None) or {})
        if extra:
            object.__setattr__(self, "broker_metadata", {**self.broker_metadata, **extra})
            object.__setattr__(self, "__pydantic_extra__", {})


def _bool_query(value: bool | None) -> str | None:
    if value is None:
        return None
    return "true" if value else "false"


class PortfolioRequest(BaseModel):
    """Query parameters for the portfolio endpoint."""

    model_config = ConfigDict(frozen=True)

    count: int | None = Field(default=None, ge=1)
    sort_by: str | None = None
    sort_order: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    market_session: str | None = None
    totals_required: bool | None = None
    lots_required: bool | None = None
    view: str | None = None

    @field_validator("sort_by", "sort_order", "market_session", "view")
    @classmethod
    def nonempty_string(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("A nonempty value is required")
        return value

    def query_params(self) -> dict[str, str | int | None]:
        return {
            "count": self.count,
            "sortBy": self.sort_by,
            "sortOrder": self.sort_order,
            "pageNumber": self.page_number,
            "marketSession": self.market_session,
            "totalsRequired": _bool_query(self.totals_required),
            "lotsRequired": _bool_query(self.lots_required),
            "view": self.view,
        }


class ProductId(BrokerModel):
    symbol: str | None = None
    type_code: str | None = Field(default=None, alias="typeCode")


class PortfolioProduct(BrokerModel):
    symbol: str | None = None
    security_type: str | None = Field(default=None, alias="securityType")
    security_sub_type: str | None = Field(default=None, alias="securitySubType")
    call_put: str | None = Field(default=None, alias="callPut")
    expiry_year: int | None = Field(default=None, alias="expiryYear")
    expiry_month: int | None = Field(default=None, alias="expiryMonth")
    expiry_day: int | None = Field(default=None, alias="expiryDay")
    strike_price: Decimal | None = Field(default=None, alias="strikePrice")
    expiry_type: str | None = Field(default=None, alias="expiryType")
    product_id: ProductId | None = Field(default=None, alias="productId")


class QuickView(BrokerModel):
    last_trade: Decimal | None = Field(default=None, alias="lastTrade")
    last_trade_time: datetime | None = Field(default=None, alias="lastTradeTime")
    change: Decimal | None = None
    change_pct: Decimal | None = Field(default=None, alias="changePct")
    volume: int | None = None
    quote_status: str | None = Field(default=None, alias="quoteStatus")
    seven_day_current_yield: Decimal | None = Field(default=None, alias="sevenDayCurrentYield")
    annual_total_return: Decimal | None = Field(default=None, alias="annualTotalReturn")
    weighted_average_maturity: Decimal | None = Field(default=None, alias="weightedAverageMaturity")

    @field_validator("last_trade_time", mode="before")
    @classmethod
    def parse_last_trade_time(cls, value: object) -> datetime | None:
        return parse_broker_datetime(value)


class PerformanceView(BrokerModel):
    change: Decimal | None = None
    change_pct: Decimal | None = Field(default=None, alias="changePct")
    last_trade: Decimal | None = Field(default=None, alias="lastTrade")
    days_gain: Decimal | None = Field(default=None, alias="daysGain")
    total_gain: Decimal | None = Field(default=None, alias="totalGain")
    total_gain_pct: Decimal | None = Field(default=None, alias="totalGainPct")
    market_value: Decimal | None = Field(default=None, alias="marketValue")
    quote_status: str | None = Field(default=None, alias="quoteStatus")
    last_trade_time: datetime | None = Field(default=None, alias="lastTradeTime")

    @field_validator("last_trade_time", mode="before")
    @classmethod
    def parse_last_trade_time(cls, value: object) -> datetime | None:
        return parse_broker_datetime(value)


class FundamentalView(BrokerModel):
    last_trade: Decimal | None = Field(default=None, alias="lastTrade")
    last_trade_time: datetime | None = Field(default=None, alias="lastTradeTime")
    change: Decimal | None = None
    change_pct: Decimal | None = Field(default=None, alias="changePct")
    pe_ratio: Decimal | None = Field(default=None, alias="peRatio")
    eps: Decimal | None = None
    dividend: Decimal | None = None
    div_yield: Decimal | None = Field(default=None, alias="divYield")
    market_cap: Decimal | None = Field(default=None, alias="marketCap")
    week52_range: str | None = Field(default=None, alias="week52Range")
    quote_status: str | None = Field(default=None, alias="quoteStatus")

    @field_validator("last_trade_time", mode="before")
    @classmethod
    def parse_last_trade_time(cls, value: object) -> datetime | None:
        return parse_broker_datetime(value)


class OptionsWatchView(BrokerModel):
    base_symbol_and_price: str | None = Field(default=None, alias="baseSymbolAndPrice")
    premium: Decimal | None = None
    last_trade: Decimal | None = Field(default=None, alias="lastTrade")
    bid: Decimal | None = None
    ask: Decimal | None = None
    quote_status: str | None = Field(default=None, alias="quoteStatus")
    last_trade_time: datetime | None = Field(default=None, alias="lastTradeTime")

    @field_validator("last_trade_time", mode="before")
    @classmethod
    def parse_last_trade_time(cls, value: object) -> datetime | None:
        return parse_broker_datetime(value)


class CompleteView(BrokerModel):
    price_adjusted_flag: bool | None = Field(default=None, alias="priceAdjustedFlag")
    price: Decimal | None = None
    adj_price: Decimal | None = Field(default=None, alias="adjPrice")
    change: Decimal | None = None
    change_pct: Decimal | None = Field(default=None, alias="changePct")
    prev_close: Decimal | None = Field(default=None, alias="prevClose")
    adj_prev_close: Decimal | None = Field(default=None, alias="adjPrevClose")
    volume: Decimal | None = None
    last_trade: Decimal | None = Field(default=None, alias="lastTrade")
    last_trade_time: datetime | None = Field(default=None, alias="lastTradeTime")
    symbol_description: str | None = Field(default=None, alias="symbolDescription")
    bid: Decimal | None = None
    ask: Decimal | None = None
    quote_status: str | None = Field(default=None, alias="quoteStatus")
    div_pay_date: date | None = Field(default=None, alias="divPayDate")
    ex_dividend_date: date | None = Field(default=None, alias="exDividendDate")

    @field_validator("last_trade_time", mode="before")
    @classmethod
    def parse_last_trade_time(cls, value: object) -> datetime | None:
        return parse_broker_datetime(value)

    @field_validator("div_pay_date", "ex_dividend_date", mode="before")
    @classmethod
    def parse_dividend_dates(cls, value: object) -> date | None:
        return parse_broker_date(value)


class PositionLot(BrokerModel):
    position_id: int | None = Field(default=None, alias="positionId")
    position_lot_id: int | None = Field(default=None, alias="positionLotId")
    price: Decimal | None = None
    term_code: int | None = Field(default=None, alias="termCode")
    days_gain: Decimal | None = Field(default=None, alias="daysGain")
    days_gain_pct: Decimal | None = Field(default=None, alias="daysGainPct")
    market_value: Decimal | None = Field(default=None, alias="marketValue")
    total_cost: Decimal | None = Field(default=None, alias="totalCost")
    total_cost_for_gain_pct: Decimal | None = Field(default=None, alias="totalCostForGainPct")
    total_gain: Decimal | None = Field(default=None, alias="totalGain")
    lot_source_code: int | None = Field(default=None, alias="lotSourceCode")
    original_qty: Decimal | None = Field(default=None, alias="originalQty")
    remaining_qty: Decimal | None = Field(default=None, alias="remainingQty")
    available_qty: Decimal | None = Field(default=None, alias="availableQty")
    order_no: int | None = Field(default=None, alias="orderNo")
    leg_no: int | None = Field(default=None, alias="legNo")
    acquired_date: date | None = Field(default=None, alias="acquiredDate")
    location_code: int | None = Field(default=None, alias="locationCode")
    exchange_rate: Decimal | None = Field(default=None, alias="exchangeRate")
    settlement_currency: str | None = Field(default=None, alias="settlementCurrency")
    payment_currency: str | None = Field(default=None, alias="paymentCurrency")
    adj_price: Decimal | None = Field(default=None, alias="adjPrice")
    comm_per_share: Decimal | None = Field(default=None, alias="commPerShare")
    fees_per_share: Decimal | None = Field(default=None, alias="feesPerShare")
    premium_adj: Decimal | None = Field(default=None, alias="premiumAdj")
    short_type: int | None = Field(default=None, alias="shortType")

    @field_validator("acquired_date", mode="before")
    @classmethod
    def parse_acquired_date(cls, value: object) -> date | None:
        return parse_broker_date(value)


def _empty_position_lots() -> list[PositionLot]:
    return []


class Position(BrokerModel):
    position_id: int | None = Field(default=None, alias="positionId")
    account_id: str | None = Field(default=None, alias="accountId")
    product: PortfolioProduct | None = Field(default=None, alias="product")
    osi_key: str | None = Field(default=None, alias="osiKey")
    symbol_description: str | None = Field(default=None, alias="symbolDescription")
    date_acquired: date | None = Field(default=None, alias="dateAcquired")
    price_paid: Decimal | None = Field(default=None, alias="pricePaid")
    price: Decimal | None = None
    commissions: Decimal | None = None
    other_fees: Decimal | None = Field(default=None, alias="otherFees")
    quantity: Decimal | None = None
    position_indicator: str | None = Field(default=None, alias="positionIndicator")
    position_type: str | None = Field(default=None, alias="positionType")
    change: Decimal | None = None
    change_pct: Decimal | None = Field(default=None, alias="changePct")
    days_gain: Decimal | None = Field(default=None, alias="daysGain")
    days_gain_pct: Decimal | None = Field(default=None, alias="daysGainPct")
    market_value: Decimal | None = Field(default=None, alias="marketValue")
    total_cost: Decimal | None = Field(default=None, alias="totalCost")
    total_gain: Decimal | None = Field(default=None, alias="totalGain")
    total_gain_pct: Decimal | None = Field(default=None, alias="totalGainPct")
    pct_of_portfolio: Decimal | None = Field(default=None, alias="pctOfPortfolio")
    cost_per_share: Decimal | None = Field(default=None, alias="costPerShare")
    quote_status: str | None = Field(default=None, alias="quoteStatus")
    date_time_utc: datetime | None = Field(default=None, alias="dateTimeUTC")
    adj_prev_close: Decimal | None = Field(default=None, alias="adjPrevClose")
    performance: PerformanceView | None = None
    fundamental: FundamentalView | None = None
    options_watch: OptionsWatchView | None = Field(default=None, alias="optionsWatch")
    quick: QuickView | None = None
    complete: CompleteView | None = None
    lots_details: str | None = Field(default=None, alias="lotsDetails")
    quote_details: str | None = Field(default=None, alias="quoteDetails")
    position_lots: list[PositionLot] = Field(
        default_factory=_empty_position_lots, alias="positionLot"
    )

    @field_validator("date_acquired", mode="before")
    @classmethod
    def parse_date_acquired(cls, value: object) -> date | None:
        return parse_broker_date(value)

    @field_validator("date_time_utc", mode="before")
    @classmethod
    def parse_date_time_utc(cls, value: object) -> datetime | None:
        return parse_broker_datetime(value)

    @model_validator(mode="before")
    @classmethod
    def normalize_nested_aliases(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        for source, target in {
            "Product": "product",
            "Performance": "performance",
            "Fundamental": "fundamental",
            "OptionsWatch": "optionsWatch",
            "Quick": "quick",
            "Complete": "complete",
            "PositionLot": "positionLot",
        }.items():
            if source in data and target not in data:
                data[target] = data[source]
            data.pop(source, None)
        return data

    @field_validator("position_lots", mode="before")
    @classmethod
    def normalize_position_lots(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        return value


def _empty_positions() -> list[Position]:
    return []


class AccountPortfolio(BrokerModel):
    account_id: str | None = Field(default=None, alias="accountId")
    next: str | None = None
    total_no_of_pages: int | None = Field(default=None, alias="totalNoOfPages")
    total_pages: int | None = Field(default=None, alias="totalPages")
    next_page_no: str | None = Field(default=None, alias="nextPageNo")
    positions: list[Position] = Field(default_factory=_empty_positions, alias="position")

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        if "Position" in data and "position" not in data:
            data["position"] = data["Position"]
        data.pop("Position", None)
        return data

    @field_validator("positions", mode="before")
    @classmethod
    def normalize_positions(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        return value


class PortfolioTotals(BrokerModel):
    todays_gain_loss: Decimal | None = Field(default=None, alias="todaysGainLoss")
    todays_gain_loss_pct: Decimal | None = Field(default=None, alias="todaysGainLossPct")
    total_market_value: Decimal | None = Field(default=None, alias="totalMarketValue")
    total_gain_loss: Decimal | None = Field(default=None, alias="totalGainLoss")
    total_gain_loss_pct: Decimal | None = Field(default=None, alias="totalGainLossPct")
    total_price_paid: Decimal | None = Field(default=None, alias="totalPricePaid")
    cash_balance: Decimal | None = Field(default=None, alias="cashBalance")


def _empty_account_portfolios() -> list[AccountPortfolio]:
    return []


class PortfolioResponse(BrokerModel):
    totals: PortfolioTotals | None = None
    account_portfolios: list[AccountPortfolio] = Field(
        default_factory=_empty_account_portfolios, alias="accountPortfolio"
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        if "Totals" in data and "totals" not in data:
            data["totals"] = data["Totals"]
        if "AccountPortfolio" in data and "accountPortfolio" not in data:
            data["accountPortfolio"] = data["AccountPortfolio"]
        data.pop("Totals", None)
        data.pop("AccountPortfolio", None)
        return data

    @field_validator("account_portfolios", mode="before")
    @classmethod
    def normalize_account_portfolios(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        return value
