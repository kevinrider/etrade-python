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
            {
                "marker": "50",
                "count": "10",
                "startDate": "01012026",
                "endDate": "01312026",
                "sortOrder": "DESC",
            }
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


@pytest.mark.parametrize("sort_order", ["ASC", None])
async def test_transactions_list_preserves_explicit_sort_order(
    settings: ETradeSettings, auth: FakeAuthenticator, sort_order: str | None
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if sort_order is None:
            assert "sortOrder" not in request.url.params
        else:
            assert request.url.params["sortOrder"] == sort_order
        return httpx.Response(204)

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        await TransactionsService(transport).list(
            "fake-key", TransactionsRequest(sort_order=sort_order)
        )


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


async def test_portfolio_validation_diagnostic_reports_field_path(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    payload = {
        "PortfolioResponse": {
            "AccountPortfolio": {
                "Position": {"Product": {"symbol": "AAPL"}, "quantity": "not-a-decimal"}
            }
        }
    }

    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)),
    ) as transport:
        with pytest.raises(ETradeResponseError) as exc:
            await PortfolioService(transport).get_positions("fake-key")

    message = str(exc.value)
    assert "Invalid portfolio response" in message
    assert "quantity" in message
    assert "not-a-decimal" not in message


async def test_transactions_validation_diagnostic_reports_field_path(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    payload = {"TransactionListResponse": {"Transaction": {"amount": "not-a-decimal"}}}

    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)),
    ) as transport:
        with pytest.raises(ETradeResponseError) as exc:
            await TransactionsService(transport).list("fake-key")

    message = str(exc.value)
    assert "Invalid transactions response" in message
    assert "amount" in message
    assert "not-a-decimal" not in message


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


async def test_transactions_list_all_follows_marker_and_preserves_filters(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.path == "/v1/accounts/fake-key/transactions.json"
        assert request.url.params == httpx.QueryParams(
            {
                "marker": "start-marker" if len(calls) == 1 else "18151100002634_1527739200",
                "count": "3",
                "startDate": "01012026",
                "endDate": "01312026",
                "sortOrder": "DESC",
            }
        )
        assert len(calls) <= 2
        fixture = (
            "responses/transactions_response.json"
            if len(calls) == 1
            else "responses/transactions_response_page2.json"
        )
        return httpx.Response(200, json=load_json_fixture(fixture))

    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(handler),
    ) as transport:
        transactions = [
            transaction
            async for transaction in TransactionsService(transport).list_all(
                "fake-key",
                TransactionsRequest(
                    marker="start-marker",
                    count=3,
                    start_date="01012026",
                    end_date="01312026",
                    sort_order="DESC",
                ),
            )
        ]

    assert len(calls) == 2
    assert [transaction.transaction_id for transaction in transactions] == [
        "18165100001766",
        "18158100000983",
        "18151100002634",
        "fake-transaction-4",
        "fake-transaction-5",
    ]


@pytest.mark.parametrize("sort_order", ["DESC", "ASC"])
async def test_transactions_list_all_omits_inclusive_boundaries(
    settings: ETradeSettings, auth: FakeAuthenticator, sort_order: str
) -> None:
    pages = load_json_fixture("responses/transactions_inclusive_pages.json")["pages"]
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        index = len(calls)
        calls.append(request)
        assert index < len(pages)
        assert request.url.params == httpx.QueryParams(
            {
                **({"marker": f"fake-page-{index}"} if index else {}),
                "count": "2",
                "sortOrder": sort_order,
            }
        )
        return httpx.Response(200, json=pages[index])

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        transactions = [
            transaction
            async for transaction in TransactionsService(transport).list_all(
                "fake-key", TransactionsRequest(count=2, sort_order=sort_order)
            )
        ]

    assert len(calls) == 4
    assert [transaction.transaction_id for transaction in transactions] == ["1", "2", "3", "4"]


async def test_transactions_list_preserves_boundary_and_permits_count_one(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    pages = load_json_fixture("responses/transactions_inclusive_pages.json")["pages"]
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.params["count"] == "1":
            payload = pages[0]["TransactionListResponse"]
            payload["Transaction"] = payload["Transaction"][:1]
            payload["transactionCount"] = "1"
            return httpx.Response(200, json=pages[0])
        return httpx.Response(200, json=pages[1])

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        service = TransactionsService(transport)
        page = await service.list("fake-key", TransactionsRequest(count=2))
        assert [transaction.transaction_id for transaction in page.transactions] == [2, "3"]
        single_page = await service.list("fake-key", TransactionsRequest(count=1))
        assert len(single_page.transactions) == 1
        with pytest.raises(ETradeValidationError, match="count >= 2"):
            await anext(service.list_all("fake-key", TransactionsRequest(count=1)))

    assert len(calls) == 2


@pytest.mark.parametrize("failure_page", [0, 1, 2])
async def test_transactions_list_all_rejects_repeated_or_cyclic_markers(
    settings: ETradeSettings, auth: FakeAuthenticator, failure_page: int
) -> None:
    pages = load_json_fixture("responses/transactions_inclusive_pages.json")["pages"]
    pages[failure_page]["TransactionListResponse"]["marker"] = "fake-page-1"
    request = TransactionsRequest(count=2, marker="fake-page-1" if failure_page == 0 else None)
    calls: list[httpx.Request] = []
    yielded_ids: list[int | str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        index = len(calls)
        calls.append(request)
        assert index <= failure_page
        return httpx.Response(200, json=pages[index])

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        with pytest.raises(ETradeResponseError, match="did not advance") as caught:
            async for transaction in TransactionsService(transport).list_all("fake-key", request):
                yielded_ids.append(transaction.transaction_id)

    assert len(calls) == failure_page + 1
    expected_ids = [[], ["1", "2"], ["1", "2", "3"]][failure_page]
    assert yielded_ids == expected_ids
    assert "fake-page-1" not in str(caught.value)
    assert "fake-key" not in str(caught.value)


async def test_transactions_list_all_only_removes_boundary_duplicates(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    pages = load_json_fixture("responses/transactions_inclusive_pages.json")["pages"]
    payload = pages[1]["TransactionListResponse"]
    payload["Transaction"][1]["transactionId"] = "1"
    payload["marker"] = None
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        index = len(calls)
        calls.append(request)
        assert index < 2
        return httpx.Response(200, json=pages[index])

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        transactions = [
            transaction
            async for transaction in TransactionsService(transport).list_all(
                "fake-key", TransactionsRequest(count=2)
            )
        ]

    assert [transaction.transaction_id for transaction in transactions] == ["1", "2", "1"]


@pytest.mark.parametrize("marker, count", [(None, 3), ("", 3), ("unused-marker", 4)])
async def test_transactions_list_all_stops_without_marker_or_on_short_page(
    settings: ETradeSettings,
    auth: FakeAuthenticator,
    marker: str | None,
    count: int,
) -> None:
    calls: list[httpx.Request] = []
    fixture = load_json_fixture("responses/transactions_response.json")
    payload = fixture["TransactionListResponse"]
    if marker is None:
        payload.pop("marker")
    else:
        payload["marker"] = marker

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert len(calls) == 1
        return httpx.Response(200, json=fixture)

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        transactions = [
            transaction
            async for transaction in TransactionsService(transport).list_all(
                "fake-key", TransactionsRequest(count=count)
            )
        ]

    assert len(calls) == 1
    assert len(transactions) == 3


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
