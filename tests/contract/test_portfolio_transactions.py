from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from etrade_python import (
    ETradeClient,
    ETradeResponseError,
    ETradeSettings,
    ETradeValidationError,
    PortfolioRequest,
    TransactionsRequest,
)
from etrade_python.portfolio import PortfolioService
from etrade_python.transactions import TransactionDetailsRequest, TransactionsService
from etrade_python.transport import ApiTransport
from tests.conftest import FakeAuthenticator, load_json_fixture


async def test_portfolio_positions_contract(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/accounts/fake-key/portfolio.json"
        assert request.url.params == httpx.QueryParams(
            {"count": "10", "totalsRequired": "true", "lotsRequired": "true", "view": "QUICK"}
        )
        return httpx.Response(200, json=load_json_fixture("responses/portfolio_response.json"))

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        response = await PortfolioService(transport).get_positions(
            "fake-key",
            PortfolioRequest(count=10, totals_required=True, lots_required=True, view="QUICK"),
        )

    assert response.account_portfolios[0].account_id == "835547880"
    assert response.totals is None
    assert len(response.account_portfolios[0].positions) == 2
    position = response.account_portfolios[0].positions[0]
    assert position.product is not None
    assert position.product.symbol == "A"
    assert position.quantity == Decimal("-120")
    assert position.market_value == Decimal("-7605.60")
    assert position.quick is not None
    assert position.quick.last_trade == Decimal("63.38")
    assert position.quick.last_trade_time == datetime(2018, 6, 19, 17, 28, tzinfo=UTC)


async def test_portfolio_rejects_blank_account_id(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ApiTransport(settings, authenticator=auth) as transport:
        with pytest.raises(ETradeValidationError, match="account_id_key"):
            await PortfolioService(transport).get_positions(" ")


async def test_transactions_list_contract(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/accounts/fake-key/transactions.json"
        assert request.url.params == httpx.QueryParams(
            {"marker": "50", "count": "10", "startDate": "01012026", "endDate": "01312026"}
        )
        return httpx.Response(200, json=load_json_fixture("responses/transactions_response.json"))

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        response = await TransactionsService(transport).list(
            "fake-key",
            TransactionsRequest(marker="50", count=10, start_date="01012026", end_date="01312026"),
        )

    assert len(response.transactions) == 3
    assert response.transaction_count == "3"
    assert response.total_count == "5"
    transaction = response.transactions[0]
    assert transaction.transaction_id == "18165100001766"
    assert transaction.transaction_date == datetime(2018, 6, 14, 4, tzinfo=UTC)
    assert transaction.amount == Decimal("-2")
    assert transaction.brokerage is not None
    assert transaction.brokerage.product is None


async def test_transaction_details_contract(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/accounts/fake-key/transactions/99.json"
        assert request.url.params == httpx.QueryParams({"storeId": "bank"})
        return httpx.Response(
            200, json=load_json_fixture("responses/transaction_details_response.json")
        )

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        response = await TransactionsService(transport).get(
            "fake-key", "99", TransactionDetailsRequest(store_id="bank")
        )

    assert response.transaction.transaction_id == "18144100000861"
    assert response.transaction.transaction_date == datetime(2018, 5, 24, 4, tzinfo=UTC)
    assert response.transaction.category is not None
    assert response.transaction.category.category_name == ""
    assert response.transaction.brokerage is not None
    assert response.transaction.brokerage.product is None


async def test_transactions_reject_blank_ids(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ApiTransport(settings, authenticator=auth) as transport:
        service = TransactionsService(transport)
        with pytest.raises(ETradeValidationError, match="account_id_key"):
            await service.list(" ")
        with pytest.raises(ETradeValidationError, match="transaction_id"):
            await service.get("fake-key", " ")


async def test_invalid_portfolio_response_is_structured(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"bad": True})),
    ) as transport:
        with pytest.raises(ETradeResponseError):
            await PortfolioService(transport).get_positions("fake-key")


async def test_client_exposes_milestone_four_services(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ETradeClient(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(lambda r: httpx.Response(204)),
    ) as client:
        assert isinstance(client.portfolio, PortfolioService)
        assert isinstance(client.transactions, TransactionsService)


async def test_portfolio_204_is_empty(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(lambda r: httpx.Response(204)),
    ) as transport:
        response = await PortfolioService(transport).get_positions("fake-key")

    assert response.account_portfolios == []


async def test_portfolio_iter_positions_follows_next_page(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        page_number = request.url.params.get("pageNumber")
        if page_number is None:
            next_value = "2"
            symbol = "AAPL"
        else:
            next_value = None
            symbol = "MSFT"
        payload: dict[str, object] = {
            "accountId": "123456",
            "Position": {"positionId": len(calls), "Product": {"symbol": symbol}},
        }
        if next_value is not None:
            payload["nextPageNo"] = next_value
        return httpx.Response(200, json={"PortfolioResponse": {"AccountPortfolio": payload}})

    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(handler),
    ) as transport:
        positions = [
            position async for position in PortfolioService(transport).iter_positions("fake-key")
        ]

    assert len(calls) == 2
    assert [position.product.symbol for position in positions if position.product is not None] == [
        "AAPL",
        "MSFT",
    ]


async def test_transactions_204_is_empty(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(lambda r: httpx.Response(204)),
    ) as transport:
        response = await TransactionsService(transport).list("fake-key")

    assert response.transactions == []


async def test_transactions_iter_all_follows_page_markers(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        marker = request.url.params.get("marker")
        if marker is None:
            transaction_id = "1"
            page_marker = "next-marker"
        else:
            transaction_id = "2"
            page_marker = None
        payload: dict[str, object] = {
            "Transaction": {"transactionId": transaction_id},
        }
        if page_marker is not None:
            payload["pageMarkers"] = page_marker
        return httpx.Response(200, json={"TransactionListResponse": payload})

    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(handler),
    ) as transport:
        transactions = [
            transaction
            async for transaction in TransactionsService(transport).iter_all(
                "fake-key", TransactionsRequest(count=1)
            )
        ]

    assert len(calls) == 2
    assert [transaction.transaction_id for transaction in transactions] == ["1", "2"]


async def test_invalid_transactions_responses_are_structured(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])),
    ) as transport:
        with pytest.raises(ETradeResponseError):
            await TransactionsService(transport).list("fake-key")
