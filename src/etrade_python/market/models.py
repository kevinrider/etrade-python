"""Typed market request and response models."""

from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from etrade_python._dates import parse_broker_datetime


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


class QuotesRequest(BaseModel):
    """Query parameters for quote lookup."""

    model_config = ConfigDict(frozen=True)

    detail_flag: str | None = None
    require_earnings_date: bool | None = None
    override_symbol_count: bool | None = None
    skip_mini_options_check: bool | None = None

    @field_validator("detail_flag")
    @classmethod
    def valid_detail_flag(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("A nonempty value is required")
        if normalized not in {"ALL", "FUNDAMENTAL", "INTRADAY", "OPTIONS", "WEEK_52", "MF_DETAIL"}:
            raise ValueError("Unsupported quote detail flag")
        return normalized

    def query_params(self) -> dict[str, str | None]:
        return {
            "detailFlag": self.detail_flag,
            "requireEarningsDate": _bool_query(self.require_earnings_date),
            "overrideSymbolCount": _bool_query(self.override_symbol_count),
            "skipMiniOptionsCheck": _bool_query(self.skip_mini_options_check),
        }


class ProductLookupRequest(BaseModel):
    """Path parameter for product lookup."""

    model_config = ConfigDict(frozen=True)

    search: str

    @field_validator("search")
    @classmethod
    def nonempty_search(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A nonempty value is required")
        return value


class OptionExpirationsRequest(BaseModel):
    """Query parameters for option expiration dates."""

    model_config = ConfigDict(frozen=True)

    expiry_type: str | None = None

    @field_validator("expiry_type")
    @classmethod
    def valid_expiry_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("A nonempty value is required")
        if normalized not in {
            "UNSPECIFIED",
            "DAILY",
            "WEEKLY",
            "MONTHLY",
            "QUARTERLY",
            "VIX",
            "ALL",
            "MONTHEND",
        }:
            raise ValueError("Unsupported option expiration type")
        return normalized

    def query_params(self, symbol: str) -> dict[str, str | None]:
        return {"symbol": symbol, "expiryType": self.expiry_type}


class OptionChainRequest(BaseModel):
    """Query parameters for option chains."""

    model_config = ConfigDict(frozen=True)

    expiry_year: int | None = Field(default=None, ge=1900)
    expiry_month: int | None = Field(default=None, ge=1, le=12)
    expiry_day: int | None = Field(default=None, ge=1, le=31)
    strike_price_near: Decimal | None = Field(default=None, ge=0)
    no_of_strikes: int | None = Field(default=None, ge=1)
    include_weekly: bool | None = None
    skip_adjusted: bool | None = None
    option_category: str | None = None
    chain_type: str | None = None
    price_type: str | None = None

    @field_validator("option_category")
    @classmethod
    def valid_option_category(cls, value: str | None) -> str | None:
        return _normalize_choice(value, {"STANDARD", "ALL", "MINI"}, "option category")

    @field_validator("chain_type")
    @classmethod
    def valid_chain_type(cls, value: str | None) -> str | None:
        return _normalize_choice(value, {"CALL", "PUT", "CALLPUT"}, "chain type")

    @field_validator("price_type")
    @classmethod
    def valid_price_type(cls, value: str | None) -> str | None:
        return _normalize_choice(value, {"ATNM", "ALL"}, "price type")

    def query_params(self, symbol: str) -> dict[str, str | int | None]:
        return {
            "symbol": symbol,
            "expiryYear": self.expiry_year,
            "expiryMonth": self.expiry_month,
            "expiryDay": self.expiry_day,
            "strikePriceNear": str(self.strike_price_near)
            if self.strike_price_near is not None
            else None,
            "noOfStrikes": self.no_of_strikes,
            "includeWeekly": _bool_query(self.include_weekly),
            "skipAdjusted": _bool_query(self.skip_adjusted),
            "optionCategory": self.option_category,
            "chainType": self.chain_type,
            "priceType": self.price_type,
        }


def _normalize_choice(value: str | None, choices: set[str], label: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        raise ValueError("A nonempty value is required")
    if normalized not in choices:
        raise ValueError(f"Unsupported {label}")
    return normalized


class ProductId(BrokerModel):
    symbol: str | None = None
    type_code: str | None = Field(default=None, alias="typeCode")


class Product(BrokerModel):
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

    @model_validator(mode="before")
    @classmethod
    def normalize_nested_aliases(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        if "ProductId" in data and "productId" not in data:
            data["productId"] = data["ProductId"]
        data.pop("ProductId", None)
        return data


class LookupProduct(BrokerModel):
    symbol: str | None = None
    description: str | None = None
    type: str | None = None


def _empty_lookup_products() -> list[LookupProduct]:
    return []


class ProductLookupResponse(BrokerModel):
    products: list[LookupProduct] = Field(default_factory=_empty_lookup_products, alias="data")

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        if "Data" in data and "data" not in data:
            data["data"] = data["Data"]
        data.pop("Data", None)
        return data

    @field_validator("products", mode="before")
    @classmethod
    def normalize_products(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        return value


class QuoteDetails(BrokerModel):
    adjusted_flag: bool | str | None = Field(default=None, alias="adjustedFlag")
    ask: Decimal | None = None
    ask_size: int | None = Field(default=None, alias="askSize")
    ask_time: datetime | None = Field(default=None, alias="askTime")
    bid: Decimal | None = None
    bid_exchange: str | None = Field(default=None, alias="bidExchange")
    bid_size: int | None = Field(default=None, alias="bidSize")
    bid_time: datetime | None = Field(default=None, alias="bidTime")
    change_close: Decimal | None = Field(default=None, alias="changeClose")
    change_close_percentage: Decimal | None = Field(default=None, alias="changeClosePercentage")
    company_name: str | None = Field(default=None, alias="companyName")
    days_to_expiration: int | None = Field(default=None, alias="daysToExpiration")
    dividend: Decimal | None = None
    eps: Decimal | None = None
    est_earnings: Decimal | None = Field(default=None, alias="estEarnings")
    ex_dividend_date: datetime | None = Field(default=None, alias="exDividendDate")
    high: Decimal | None = None
    high52: Decimal | None = None
    last_trade: Decimal | None = Field(default=None, alias="lastTrade")
    low: Decimal | None = None
    low52: Decimal | None = None
    open: Decimal | None = None
    open_interest: int | None = Field(default=None, alias="openInterest")
    option_style: str | None = Field(default=None, alias="optionStyle")
    option_underlier: str | None = Field(default=None, alias="optionUnderlier")
    previous_close: Decimal | None = Field(default=None, alias="previousClose")
    previous_day_volume: int | None = Field(default=None, alias="previousDayVolume")
    primary_exchange: str | None = Field(default=None, alias="primaryExchange")
    symbol_description: str | None = Field(default=None, alias="symbolDescription")
    total_volume: int | None = Field(default=None, alias="totalVolume")
    market_cap: Decimal | None = Field(default=None, alias="marketCap")
    shares_outstanding: Decimal | None = Field(default=None, alias="sharesOutstanding")
    next_earning_date: datetime | None = Field(default=None, alias="nextEarningDate")
    beta: Decimal | None = None
    yield_: Decimal | None = Field(default=None, alias="yield")
    declared_dividend: Decimal | None = Field(default=None, alias="declaredDividend")
    dividend_payable_date: datetime | None = Field(default=None, alias="dividendPayableDate")
    pe: Decimal | None = None
    week52_low_date: datetime | None = Field(default=None, alias="week52LowDate")
    week52_hi_date: datetime | None = Field(default=None, alias="week52HiDate")
    intrinsic_value: Decimal | None = Field(default=None, alias="intrinsicValue")
    time_premium: Decimal | None = Field(default=None, alias="timePremium")
    option_multiplier: Decimal | None = Field(default=None, alias="optionMultiplier")
    contract_size: Decimal | None = Field(default=None, alias="contractSize")
    expiration_date: datetime | None = Field(default=None, alias="expirationDate")
    time_of_last_trade: datetime | None = Field(default=None, alias="timeOfLastTrade")
    average_volume: int | None = Field(default=None, alias="averageVolume")

    @field_validator(
        "ask_time",
        "bid_time",
        "ex_dividend_date",
        "next_earning_date",
        "dividend_payable_date",
        "week52_low_date",
        "week52_hi_date",
        "expiration_date",
        "time_of_last_trade",
        mode="before",
    )
    @classmethod
    def parse_detail_datetimes(cls, value: object) -> datetime | None:
        return parse_broker_datetime(value)


class Quote(BrokerModel):
    date_time: datetime | None = Field(default=None, alias="dateTime")
    date_time_utc: datetime | None = Field(default=None, alias="dateTimeUTC")
    quote_status: str | None = Field(default=None, alias="quoteStatus")
    ah_flag: bool | str | None = Field(default=None, alias="ahFlag")
    error_message: str | None = Field(default=None, alias="errorMessage")
    time_zone: str | None = Field(default=None, alias="timeZone")
    dst_flag: bool | str | None = Field(default=None, alias="dstFlag")
    has_mini_options: bool | str | None = Field(default=None, alias="hasMiniOptions")
    all: QuoteDetails | None = None
    fundamental: QuoteDetails | None = None
    intraday: QuoteDetails | None = None
    option: QuoteDetails | None = None
    week52: QuoteDetails | None = Field(default=None, alias="week52")
    mutual_fund: QuoteDetails | None = Field(default=None, alias="mutualFund")
    product: Product | None = None

    @field_validator("date_time", "date_time_utc", mode="before")
    @classmethod
    def parse_quote_datetimes(cls, value: object) -> datetime | None:
        return parse_broker_datetime(value)

    @model_validator(mode="before")
    @classmethod
    def normalize_nested_aliases(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        aliases = {
            "All": "all",
            "Fundamental": "fundamental",
            "Intraday": "intraday",
            "Option": "option",
            "Week52": "week52",
            "MutualFund": "mutualFund",
            "Product": "product",
        }
        for source, target in aliases.items():
            if source in data and target not in data:
                data[target] = data[source]
            data.pop(source, None)
        return data


def _empty_quotes() -> list[Quote]:
    return []


class QuotesResponse(BrokerModel):
    quotes: list[Quote] = Field(default_factory=_empty_quotes, alias="quoteData")

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        if "QuoteData" in data and "quoteData" not in data:
            data["quoteData"] = data["QuoteData"]
        data.pop("QuoteData", None)
        return data

    @field_validator("quotes", mode="before")
    @classmethod
    def normalize_quotes(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        return value


class OptionExpiration(BrokerModel):
    year: int | None = None
    month: int | None = None
    day: int | None = None
    expiry_type: str | None = Field(default=None, alias="expiryType")


def _empty_option_expirations() -> list[OptionExpiration]:
    return []


class OptionExpirationsResponse(BrokerModel):
    expiration_dates: list[OptionExpiration] = Field(
        default_factory=_empty_option_expirations, alias="expirationDates"
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        for source in ("ExpirationDates", "ExpirationDate", "expirationDate"):
            if source in data and "expirationDates" not in data:
                data["expirationDates"] = data[source]
            data.pop(source, None)
        return data

    @field_validator("expiration_dates", mode="before")
    @classmethod
    def normalize_expiration_dates(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        return value


class OptionGreeks(BrokerModel):
    rho: Decimal | None = None
    vega: Decimal | None = None
    theta: Decimal | None = None
    delta: Decimal | None = None
    gamma: Decimal | None = None
    iv: Decimal | None = None
    current_value: bool | str | None = Field(default=None, alias="currentValue")


class OptionContract(BrokerModel):
    option_category: str | None = Field(default=None, alias="optionCategory")
    option_root_symbol: str | None = Field(default=None, alias="optionRootSymbol")
    time_stamp: datetime | None = Field(default=None, alias="timeStamp")
    adjusted_flag: bool | str | None = Field(default=None, alias="adjustedFlag")
    display_symbol: str | None = Field(default=None, alias="displaySymbol")
    option_type: str | None = Field(default=None, alias="optionType")
    strike_price: Decimal | None = Field(default=None, alias="strikePrice")
    symbol: str | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    bid_size: int | None = Field(default=None, alias="bidSize")
    ask_size: int | None = Field(default=None, alias="askSize")
    in_the_money: str | None = Field(default=None, alias="inTheMoney")
    volume: int | None = None
    open_interest: int | None = Field(default=None, alias="openInterest")
    net_change: Decimal | None = Field(default=None, alias="netChange")
    last_price: Decimal | None = Field(default=None, alias="lastPrice")
    quote_detail: str | None = Field(default=None, alias="quoteDetail")
    osi_key: str | None = Field(default=None, alias="osiKey")
    option_greek: OptionGreeks | None = Field(default=None, alias="optionGreek")

    @field_validator("time_stamp", mode="before")
    @classmethod
    def parse_time_stamp(cls, value: object) -> datetime | None:
        return parse_broker_datetime(value)

    @model_validator(mode="before")
    @classmethod
    def normalize_nested_aliases(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        for source in ("OptionGreeks", "optionGreeks"):
            if source in data and "optionGreek" not in data:
                data["optionGreek"] = data[source]
            data.pop(source, None)
        return data


class OptionChainPair(BrokerModel):
    call: OptionContract | None = None
    put: OptionContract | None = None
    pair_type: str | None = Field(default=None, alias="pairType")

    @model_validator(mode="before")
    @classmethod
    def normalize_nested_aliases(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        for source, target in {
            "Call": "call",
            "OptionCall": "call",
            "optioncall": "call",
            "Put": "put",
            "OptionPut": "put",
            "optionPut": "put",
        }.items():
            if source in data and target not in data:
                data[target] = data[source]
            data.pop(source, None)
        return data


class SelectedExpiration(BrokerModel):
    month: int | None = None
    year: int | None = None
    day: int | None = None


def _empty_option_pairs() -> list[OptionChainPair]:
    return []


class OptionChainResponse(BrokerModel):
    option_pairs: list[OptionChainPair] = Field(
        default_factory=_empty_option_pairs, alias="optionPairs"
    )
    time_stamp: datetime | None = Field(default=None, alias="timeStamp")
    quote_type: str | None = Field(default=None, alias="quoteType")
    near_price: Decimal | None = Field(default=None, alias="nearPrice")
    selected: SelectedExpiration | None = None

    @field_validator("time_stamp", mode="before")
    @classmethod
    def parse_time_stamp(cls, value: object) -> datetime | None:
        return parse_broker_datetime(value)

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        for source in ("OptionPairs", "OptionPair", "optionPair"):
            if source in data and "optionPairs" not in data:
                data["optionPairs"] = data[source]
            data.pop(source, None)
        if "SelectedED" in data and "selected" not in data:
            data["selected"] = data["SelectedED"]
        data.pop("SelectedED", None)
        return data

    @field_validator("option_pairs", mode="before")
    @classmethod
    def normalize_option_pairs(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        return value
