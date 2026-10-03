"""Typed transaction request and response models."""

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


class TransactionsRequest(BaseModel):
    """Query parameters for list transactions."""

    model_config = ConfigDict(frozen=True)

    marker: str | None = None
    count: int | None = Field(default=None, ge=1, le=50)
    start_date: str | None = None
    end_date: str | None = None
    sort_order: str | None = None

    @field_validator("marker", "start_date", "end_date", "sort_order")
    @classmethod
    def nonempty_string(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("A nonempty value is required")
        return value

    @model_validator(mode="after")
    def validate_date_range(self) -> "TransactionsRequest":
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("start_date and end_date must be supplied together")
        return self

    def query_params(self) -> dict[str, str | int | None]:
        return {
            "marker": self.marker,
            "count": self.count,
            "startDate": self.start_date,
            "endDate": self.end_date,
            "sortOrder": self.sort_order,
        }


class TransactionDetailsRequest(BaseModel):
    """Query parameters for transaction detail lookup."""

    model_config = ConfigDict(frozen=True)

    store_id: str | None = None

    @field_validator("store_id")
    @classmethod
    def nonempty_string(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("A nonempty value is required")
        return value

    def query_params(self) -> dict[str, str | None]:
        return {"storeId": self.store_id}


class ProductId(BrokerModel):
    symbol: str | None = None
    type_code: str | None = Field(default=None, alias="typeCode")


class TransactionProduct(BrokerModel):
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


class TransactionCategory(BrokerModel):
    category_id: int | str | None = Field(default=None, alias="categoryId")
    parent_id: int | str | None = Field(default=None, alias="parentId")
    category_name: str | None = Field(default=None, alias="categoryName")
    parent_name: str | None = Field(default=None, alias="parentName")


class TransactionBrokerage(BrokerModel):
    transaction_type: str | None = Field(default=None, alias="transactionType")
    product: TransactionProduct | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    settlement_currency: str | None = Field(default=None, alias="settlementCurrency")
    payment_currency: str | None = Field(default=None, alias="paymentCurrency")
    fee: Decimal | None = None
    memo: str | None = None
    check_no: int | str | None = Field(default=None, alias="checkNo")
    order_no: int | str | None = Field(default=None, alias="orderNo")

    @model_validator(mode="before")
    @classmethod
    def normalize_product(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        if "Product" in data and "product" not in data:
            data["product"] = data["Product"]
        data.pop("Product", None)
        if data.get("product") == {}:
            data["product"] = None
        return data


class Transaction(BrokerModel):
    transaction_id: int | str | None = Field(default=None, alias="transactionId")
    account_id: int | str | None = Field(default=None, alias="accountId")
    transaction_date: datetime | None = Field(default=None, alias="transactionDate")
    post_date: datetime | None = Field(default=None, alias="postDate")
    amount: Decimal | None = None
    description: str | None = None
    transaction_type: str | None = Field(default=None, alias="transactionType")
    inst_type: str | None = Field(default=None, alias="instType")
    store_id: int | str | None = Field(default=None, alias="storeId")
    category: TransactionCategory | None = None
    brokerage: TransactionBrokerage | None = None

    @field_validator("transaction_date", "post_date", mode="before")
    @classmethod
    def parse_transaction_dates(cls, value: object) -> datetime | None:
        return parse_broker_datetime(value)

    @model_validator(mode="before")
    @classmethod
    def normalize_nested_aliases(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        for source, target in {"Category": "category", "Brokerage": "brokerage"}.items():
            if source in data and target not in data:
                data[target] = data[source]
            data.pop(source, None)
            if data.get(target) == {}:
                data[target] = None
        return data


def _empty_transactions() -> list[Transaction]:
    return []


class TransactionsResponse(BrokerModel):
    transactions: list[Transaction] = Field(
        default_factory=_empty_transactions, alias="transaction"
    )
    page_markers: str | None = Field(default=None, alias="pageMarkers")
    more_transactions: bool | str | None = Field(default=None, alias="moreTransactions")
    transaction_count: int | str | None = Field(default=None, alias="transactionCount")
    total_count: int | str | None = Field(default=None, alias="totalCount")

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        if "Transaction" in data and "transaction" not in data:
            data["transaction"] = data["Transaction"]
        data.pop("Transaction", None)
        return data

    @field_validator("transactions", mode="before")
    @classmethod
    def normalize_transactions(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            return [cast(dict[str, Any], value)]
        return value


class TransactionDetailsResponse(BrokerModel):
    transaction: Transaction

    @model_validator(mode="before")
    @classmethod
    def normalize_response(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = cast(dict[str, Any], value)
        if "transaction" in data:
            return data
        return {"transaction": data}
