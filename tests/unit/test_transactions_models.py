from datetime import UTC, datetime
from decimal import Decimal

import pytest

from etrade_python import (
    TransactionDetailsRequest,
    TransactionDetailsResponse,
    TransactionsRequest,
    TransactionsResponse,
)
from tests.conftest import load_json_fixture


def test_transactions_response_parses_continuation_fields() -> None:
    payload = load_json_fixture("responses/transactions_response.json")["TransactionListResponse"]
    response = TransactionsResponse.model_validate(payload)

    assert response.marker == "18151100002634_1527739200"
    assert response.next == payload["next"]
    assert response.page_markers == payload["pageMarkers"]
    assert response.marker != response.page_markers
    assert response.model_dump()["marker"] == response.marker
    assert response.model_dump()["next"] == response.next


def test_transactions_request_query_params() -> None:
    request = TransactionsRequest(
        marker="123",
        count=10,
        start_date="01012026",
        end_date="01312026",
        sort_order="DESC",
    )

    assert request.query_params() == {
        "marker": "123",
        "count": 10,
        "startDate": "01012026",
        "endDate": "01312026",
        "sortOrder": "DESC",
    }


def test_transactions_request_defaults_to_descending_order() -> None:
    request = TransactionsRequest()

    assert request.sort_order == "DESC"
    assert request.query_params()["sortOrder"] == "DESC"


@pytest.mark.parametrize("sort_order", ["ASC", None])
def test_transactions_request_preserves_explicit_sort_order(sort_order: str | None) -> None:
    request = TransactionsRequest(sort_order=sort_order)

    assert request.query_params()["sortOrder"] == sort_order


def test_transactions_request_requires_date_pair() -> None:
    with pytest.raises(ValueError, match="start_date and end_date"):
        TransactionsRequest(start_date="01012026")


def test_transaction_details_request_query_params() -> None:
    assert TransactionDetailsRequest(store_id="bank").query_params() == {"storeId": "bank"}


def test_transactions_response_parses_nested_aliases_and_decimals() -> None:
    response = TransactionsResponse.model_validate(
        {
            "Transaction": {
                "transactionId": "99",
                "transactionDate": 1767225600000,
                "postDate": 1767312000000,
                "amount": "-12.34",
                "Category": {"categoryName": "Dividends"},
                "Brokerage": {
                    "transactionType": "Bought",
                    "Product": {"symbol": "MSFT", "securityType": "EQ"},
                    "quantity": "1",
                    "price": "100.50",
                },
                "futureField": "kept",
            },
            "pageMarkers": "88",
        }
    )

    transaction = response.transactions[0]
    assert response.page_markers == "88"
    assert transaction.transaction_date == datetime(2026, 1, 1, tzinfo=UTC)
    assert transaction.post_date == datetime(2026, 1, 2, tzinfo=UTC)
    assert transaction.amount == Decimal("-12.34")
    assert transaction.category is not None
    assert transaction.category.category_name == "Dividends"
    assert transaction.brokerage is not None
    assert transaction.brokerage.price == Decimal("100.50")
    assert transaction.brokerage.product is not None
    assert transaction.brokerage.product.symbol == "MSFT"
    assert not hasattr(transaction, "futureField")
    assert "futureField" not in transaction.model_dump(by_alias=True)


def test_transaction_details_response_wraps_transaction_payload() -> None:
    response = TransactionDetailsResponse.model_validate({"transactionId": "99", "amount": "1.23"})

    assert response.transaction.transaction_id == "99"
    assert response.transaction.amount == Decimal("1.23")
