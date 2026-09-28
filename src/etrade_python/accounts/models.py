"""Typed account request and response models."""

from decimal import Decimal
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BrokerModel(BaseModel):
    """Base model that preserves unmodeled broker fields."""

    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True)

    broker_metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        extra = cast(dict[str, Any], getattr(self, "__pydantic_extra__", None) or {})
        if extra:
            object.__setattr__(self, "broker_metadata", {**self.broker_metadata, **extra})
            object.__setattr__(self, "__pydantic_extra__", {})


class AccountBalanceRequest(BaseModel):
    """Query parameters for the account balance endpoint."""

    model_config = ConfigDict(frozen=True)

    inst_type: str = "BROKERAGE"
    account_type: str | None = None
    real_time_nav: bool = False

    @field_validator("inst_type", "account_type")
    @classmethod
    def nonempty_string(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("A nonempty value is required")
        return value

    def query_params(self) -> dict[str, str | bool | None]:
        return {
            "instType": self.inst_type,
            "accountType": self.account_type,
            "realTimeNAV": self.real_time_nav,
        }


class Account(BrokerModel):
    inst_no: int | None = Field(default=None, alias="instNo")
    account_id: str = Field(alias="accountId")
    account_id_key: str = Field(alias="accountIdKey")
    account_mode: str | None = Field(default=None, alias="accountMode")
    account_desc: str | None = Field(default=None, alias="accountDesc")
    account_name: str | None = Field(default=None, alias="accountName")
    account_type: str | None = Field(default=None, alias="accountType")
    institution_type: str | None = Field(default=None, alias="institutionType")
    account_status: str | None = Field(default=None, alias="accountStatus")
    closed_date: int | None = Field(default=None, alias="closedDate")
    shareworks_account: bool | None = Field(default=None, alias="shareWorksAccount")
    shareworks_source: str | None = Field(default=None, alias="shareWorksSource")
    fc_managed_mssb_closed_account: bool | None = Field(
        default=None, alias="fcManagedMssbClosedAccount"
    )


def _empty_accounts() -> list[Account]:
    return []


class AccountListResponse(BrokerModel):
    accounts: list[Account] = Field(default_factory=_empty_accounts)


class CashBalance(BrokerModel):
    funds_for_open_orders_cash: Decimal | None = Field(default=None, alias="fundsForOpenOrdersCash")
    money_market_balance: Decimal | None = Field(default=None, alias="moneyMktBalance")


class OpenCalls(BrokerModel):
    min_equity_call: Decimal | None = Field(default=None, alias="minEquityCall")
    fed_call: Decimal | None = Field(default=None, alias="fedCall")
    cash_call: Decimal | None = Field(default=None, alias="cashCall")
    house_call: Decimal | None = Field(default=None, alias="houseCall")


class RealTimeValues(BrokerModel):
    total_account_value: Decimal | None = Field(default=None, alias="totalAccountValue")
    net_market_value: Decimal | None = Field(default=None, alias="netMv")
    net_market_value_long: Decimal | None = Field(default=None, alias="netMvLong")
    net_market_value_short: Decimal | None = Field(default=None, alias="netMvShort")
    total_long_value: Decimal | None = Field(default=None, alias="totalLongValue")


class PortfolioMargin(BrokerModel):
    dt_cash_open_order_reserve: Decimal | None = Field(default=None, alias="dtCashOpenOrderReserve")
    dt_margin_open_order_reserve: Decimal | None = Field(
        default=None, alias="dtMarginOpenOrderReserve"
    )
    liquidating_equity: Decimal | None = Field(default=None, alias="liquidatingEquity")
    house_excess_equity: Decimal | None = Field(default=None, alias="houseExcessEquity")
    total_house_requirement: Decimal | None = Field(default=None, alias="totalHouseRequirement")
    excess_equity_minus_requirement: Decimal | None = Field(
        default=None, alias="excessEquityMinusRequirement"
    )
    total_margin_requirements: Decimal | None = Field(default=None, alias="totalMarginRqmts")
    available_excess_equity: Decimal | None = Field(default=None, alias="availExcessEquity")
    excess_equity: Decimal | None = Field(default=None, alias="excessEquity")
    open_order_reserve: Decimal | None = Field(default=None, alias="openOrderReserve")
    funds_on_hold: Decimal | None = Field(default=None, alias="fundsOnHold")


class ComputedBalance(BrokerModel):
    cash_available_for_investment: Decimal | None = Field(
        default=None, alias="cashAvailableForInvestment"
    )
    cash_available_for_withdrawal: Decimal | None = Field(
        default=None, alias="cashAvailableForWithdrawal"
    )
    total_available_for_withdrawal: Decimal | None = Field(
        default=None, alias="totalAvailableForWithdrawal"
    )
    net_cash: Decimal | None = Field(default=None, alias="netCash")
    cash_balance: Decimal | None = Field(default=None, alias="cashBalance")
    settled_cash_for_investment: Decimal | None = Field(
        default=None, alias="settledCashForInvestment"
    )
    unsettled_cash_for_investment: Decimal | None = Field(
        default=None, alias="unSettledCashForInvestment"
    )
    funds_withheld_from_purchase_power: Decimal | None = Field(
        default=None, alias="fundsWithheldFromPurchasePower"
    )
    funds_withheld_from_withdrawal: Decimal | None = Field(
        default=None, alias="fundsWithheldFromWithdrawal"
    )
    margin_buying_power: Decimal | None = Field(default=None, alias="marginBuyingPower")
    cash_buying_power: Decimal | None = Field(default=None, alias="cashBuyingPower")
    day_trade_margin_buying_power: Decimal | None = Field(default=None, alias="dtMarginBuyingPower")
    day_trade_cash_buying_power: Decimal | None = Field(default=None, alias="dtCashBuyingPower")
    margin_balance: Decimal | None = Field(default=None, alias="marginBalance")
    short_adjust_balance: Decimal | None = Field(default=None, alias="shortAdjustBalance")
    regulation_t_equity: Decimal | None = Field(default=None, alias="regtEquity")
    regulation_t_equity_percent: Decimal | None = Field(default=None, alias="regtEquityPercent")
    account_balance: Decimal | None = Field(default=None, alias="accountBalance")
    open_calls: OpenCalls | None = Field(default=None, alias="openCalls")
    real_time_values: RealTimeValues | None = Field(default=None, alias="realTimeValues")
    portfolio_margin: PortfolioMargin | None = Field(default=None, alias="portfolioMargin")


class LendingBalance(BrokerModel):
    current_balance: Decimal | None = Field(default=None, alias="currentBalance")
    credit_line: Decimal | None = Field(default=None, alias="creditLine")
    outstanding_balance: Decimal | None = Field(default=None, alias="outstandingBalance")
    minimum_payment_due: Decimal | None = Field(default=None, alias="minPaymentDue")
    amount_past_due: Decimal | None = Field(default=None, alias="amountPastDue")
    available_credit: Decimal | None = Field(default=None, alias="availableCredit")
    ytd_interest_paid: Decimal | None = Field(default=None, alias="ytdInterestPaid")
    last_ytd_interest_paid: Decimal | None = Field(default=None, alias="lastYtdInterestPaid")
    payment_due_date: int | None = Field(default=None, alias="paymentDueDate")
    last_payment_received_date: int | None = Field(default=None, alias="lastPaymentReceivedDate")
    payment_received_month_to_date: Decimal | None = Field(default=None, alias="paymentReceivedMtd")


class MarginBalance(BrokerModel):
    dt_cash_open_order_reserve: Decimal | None = Field(default=None, alias="dtCashOpenOrderReserve")
    dt_margin_open_order_reserve: Decimal | None = Field(
        default=None, alias="dtMarginOpenOrderReserve"
    )


class AccountBalanceResponse(BrokerModel):
    account_id: str = Field(alias="accountId")
    institution_type: str | None = Field(default=None, alias="institutionType")
    as_of_date: int | None = Field(default=None, alias="asOfDate")
    account_type: str | None = Field(default=None, alias="accountType")
    option_level: str | None = Field(default=None, alias="optionLevel")
    account_description: str | None = Field(default=None, alias="accountDescription")
    quote_mode: int | None = Field(default=None, alias="quoteMode")
    day_trader_status: str | None = Field(default=None, alias="dayTraderStatus")
    account_mode: str | None = Field(default=None, alias="accountMode")
    account_desc: str | None = Field(default=None, alias="accountDesc")
    open_calls: list[OpenCalls] = Field(default_factory=lambda: [], alias="openCalls")
    cash: CashBalance | None = Field(default=None, alias="cash")
    margin: MarginBalance | None = Field(default=None, alias="margin")
    lending: LendingBalance | None = Field(default=None, alias="lending")
    computed_balance: ComputedBalance | None = Field(default=None, alias="computedBalance")

    @field_validator("open_calls", mode="before")
    @classmethod
    def normalize_open_calls(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        return value
