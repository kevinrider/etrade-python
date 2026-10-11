"""HTTP success requires recognizable response structures, not just a 200 status."""

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from etrade_python import (
    ETradeClient,
    ETradeResponseError,
    ETradeSettings,
    PlaceOrderRequest,
    PreviewOrderRequest,
)
from tests.conftest import FakeAuthenticator, load_json_fixture

Operation = Callable[[ETradeClient], Awaitable[BaseModel]]


def preview_request() -> PreviewOrderRequest:
    return PreviewOrderRequest.model_validate(
        load_json_fixture("responses/preview_order_request_equity.json")["PreviewOrderRequest"]
    )


def place_request() -> PlaceOrderRequest:
    return PlaceOrderRequest.model_validate(
        load_json_fixture("responses/place_order_request_equity.json")["PlaceOrderRequest"]
    )


# Each entry exercises the public HTTP parser, including both change operations.
ENDPOINTS: dict[str, tuple[str, str, Operation]] = {
    "accounts.list": (
        "AccountListResponse",
        "account_list_response.json",
        lambda c: c.accounts.list(),
    ),
    "accounts.balance": (
        "BalanceResponse",
        "account_balance_response.json",
        lambda c: c.accounts.get_balance("fake-key"),
    ),
    "portfolio.positions": (
        "PortfolioResponse",
        "portfolio_response.json",
        lambda c: c.portfolio.get_positions("fake-key"),
    ),
    "transactions.list": (
        "TransactionListResponse",
        "transactions_response.json",
        lambda c: c.transactions.list("fake-key"),
    ),
    "transactions.get": (
        "TransactionDetailsResponse",
        "transaction_details_response.json",
        lambda c: c.transactions.get("fake-key", "fake-transaction"),
    ),
    "market.quotes": (
        "QuoteResponse",
        "quote_response.json",
        lambda c: c.market.get_quotes(["AAPL"]),
    ),
    "market.lookup": (
        "LookupResponse",
        "product_lookup_response.json",
        lambda c: c.market.lookup_product("AAPL"),
    ),
    "market.expirations": (
        "OptionExpireDateResponse",
        "option_expirations_response.json",
        lambda c: c.market.get_option_expirations("AAPL"),
    ),
    "market.chain": (
        "OptionChainResponse",
        "option_chain_response.json",
        lambda c: c.market.get_option_chain("AAPL"),
    ),
    "orders.list": ("OrdersResponse", "orders_response.json", lambda c: c.orders.list("fake-key")),
    "orders.preview": (
        "PreviewOrderResponse",
        "preview_order_response_equity.json",
        lambda c: c.orders.preview("fake-key", preview_request()),
    ),
    "orders.place": (
        "PlaceOrderResponse",
        "place_order_response_equity.json",
        lambda c: c.orders.place("fake-key", place_request()),
    ),
    "orders.preview_change": (
        "PreviewOrderResponse",
        "change_preview_order_response.json",
        lambda c: c.orders.preview_change("fake-key", 1, preview_request()),
    ),
    "orders.place_change": (
        "PlaceOrderResponse",
        "place_change_order_response.json",
        lambda c: c.orders.place_change("fake-key", 1, place_request()),
    ),
    "orders.cancel": (
        "CancelOrderResponse",
        "cancel_order_response.json",
        lambda c: c.orders.cancel("fake-key", 1),
    ),
    "alerts.list": ("AlertsResponse", "alerts_response.json", lambda c: c.alerts.list()),
    "alerts.get": (
        "AlertDetailsResponse",
        "alert_details_response.json",
        lambda c: c.alerts.get(1),
    ),
    "alerts.delete": (
        "DeleteAlertsResponse",
        "delete_alerts_response.json",
        lambda c: c.alerts.delete(1),
    ),
}


async def call_with_response(
    settings: ETradeSettings, auth: FakeAuthenticator, endpoint: str, response: httpx.Response
) -> BaseModel:
    async with ETradeClient(
        settings, authenticator=auth, http_transport=httpx.MockTransport(lambda r: response)
    ) as client:
        return await ENDPOINTS[endpoint][2](client)


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize(
    "shape",
    [
        "unrelated",
        "empty",
        "empty-envelope",
        "unrelated-envelope",
        "wrong-envelope",
        "list",
        "scalar",
        "null",
        "empty-body",
    ],
)
async def test_unexpected_success_shapes_are_rejected(
    settings: ETradeSettings, auth: FakeAuthenticator, endpoint: str, shape: str
) -> None:
    envelope = ENDPOINTS[endpoint][0]
    secret = {"unknown-secret-key": "fake-sensitive-value"}
    shapes: dict[str, Any] = {
        "unrelated": secret,
        "empty": {},
        "empty-envelope": {envelope: {}},
        "unrelated-envelope": {envelope: secret},
        "wrong-envelope": {"WrongResponse": secret},
        "list": [secret],
        "scalar": "fake-sensitive-value",
    }
    if shape == "null":
        response = httpx.Response(
            200, content=b"null", headers={"content-type": "application/json"}
        )
    elif shape == "empty-body":
        response = httpx.Response(200)
    else:
        response = httpx.Response(200, json=shapes[shape])
    with pytest.raises(ETradeResponseError) as exc:
        await call_with_response(settings, auth, endpoint, response)
    assert "fake-sensitive-value" not in str(exc.value)
    assert "unknown-secret-key" not in str(exc.value)


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("wrapped", [True, False])
async def test_valid_shapes_and_unknown_additions_remain_supported(
    settings: ETradeSettings, auth: FakeAuthenticator, endpoint: str, wrapped: bool
) -> None:
    envelope, fixture, _ = ENDPOINTS[endpoint]
    original = load_json_fixture(f"responses/{fixture}")
    baseline = await call_with_response(
        settings, auth, endpoint, httpx.Response(200, json=original)
    )
    payload = original[envelope]
    payload["futureField"] = "discarded"
    supplied = {envelope: payload} if wrapped else payload
    parsed = await call_with_response(settings, auth, endpoint, httpx.Response(200, json=supplied))
    assert parsed == baseline


EMPTY_COLLECTIONS: dict[str, dict[str, Any]] = {
    "accounts.list": {"Accounts": {"Account": []}},
    "portfolio.positions": {"AccountPortfolio": []},
    "transactions.list": {"Transaction": []},
    "market.quotes": {"QuoteData": []},
    "market.lookup": {"Data": []},
    "market.expirations": {"ExpirationDate": []},
    "market.chain": {"OptionPair": []},
    "orders.list": {"Order": []},
    "alerts.list": {"Alert": []},
}


@pytest.mark.parametrize("endpoint", EMPTY_COLLECTIONS)
async def test_explicit_empty_collections_are_valid(
    settings: ETradeSettings, auth: FakeAuthenticator, endpoint: str
) -> None:
    envelope = ENDPOINTS[endpoint][0]
    await call_with_response(
        settings, auth, endpoint, httpx.Response(200, json={envelope: EMPTY_COLLECTIONS[endpoint]})
    )


@pytest.mark.parametrize(
    "endpoint",
    ["accounts.list", "portfolio.positions", "transactions.list", "orders.list", "alerts.list"],
)
async def test_supported_204_lists_are_empty(
    settings: ETradeSettings, auth: FakeAuthenticator, endpoint: str
) -> None:
    await call_with_response(settings, auth, endpoint, httpx.Response(204))


@pytest.mark.parametrize(
    "endpoint",
    [
        name
        for name in ENDPOINTS
        if name
        not in {
            "accounts.list",
            "portfolio.positions",
            "transactions.list",
            "orders.list",
            "alerts.list",
        }
    ],
)
async def test_other_endpoints_reject_no_content(
    settings: ETradeSettings, auth: FakeAuthenticator, endpoint: str
) -> None:
    with pytest.raises(ETradeResponseError):
        await call_with_response(settings, auth, endpoint, httpx.Response(204))


@pytest.mark.parametrize(
    "endpoint, payload",
    [
        ("accounts.list", {"Accounts": {"unknown-secret-key": "fake-sensitive-value"}}),
        ("accounts.balance", {"Cash": {"unknown-secret-key": "fake-sensitive-value"}}),
        (
            "portfolio.positions",
            {"AccountPortfolio": [{"Position": [{"unknown-secret-key": "fake-sensitive-value"}]}]},
        ),
        ("transactions.list", {"Transaction": [{"unknown-secret-key": "fake-sensitive-value"}]}),
        ("transactions.get", {"transaction": {"unknown-secret-key": "fake-sensitive-value"}}),
        (
            "market.quotes",
            {"QuoteData": [{"Product": {"unknown-secret-key": "fake-sensitive-value"}}]},
        ),
        ("market.lookup", {"Data": [{"unknown-secret-key": "fake-sensitive-value"}]}),
        (
            "market.expirations",
            {"ExpirationDate": [{"unknown-secret-key": "fake-sensitive-value"}]},
        ),
        (
            "market.chain",
            {"OptionPair": [{"Call": {"unknown-secret-key": "fake-sensitive-value"}}]},
        ),
        ("orders.list", {"Order": [{"unknown-secret-key": "fake-sensitive-value"}]}),
        (
            "orders.preview",
            {
                "PreviewIds": [{"previewId": 1}],
                "Order": [{"unknown-secret-key": "fake-sensitive-value"}],
            },
        ),
        (
            "orders.place",
            {
                "OrderIds": [{"orderId": 1}],
                "Order": [{"unknown-secret-key": "fake-sensitive-value"}],
            },
        ),
        ("alerts.list", {"Alert": [{"unknown-secret-key": "fake-sensitive-value"}]}),
        ("alerts.get", {"unknown-secret-key": "fake-sensitive-value"}),
        (
            "alerts.delete",
            {"result": "SUCCESS", "FailedAlerts": {"unknown-secret-key": "fake-sensitive-value"}},
        ),
    ],
)
async def test_unrecognized_nested_objects_are_rejected(
    settings: ETradeSettings, auth: FakeAuthenticator, endpoint: str, payload: dict[str, object]
) -> None:
    envelope = ENDPOINTS[endpoint][0]
    with pytest.raises(ETradeResponseError) as exc:
        await call_with_response(
            settings, auth, endpoint, httpx.Response(200, json={envelope: payload})
        )
    assert "fake-sensitive-value" not in str(exc.value)
    assert "unknown-secret-key" not in str(exc.value)


@pytest.mark.parametrize(
    "endpoint, field",
    [
        ("orders.preview", "PreviewIds"),
        ("orders.preview_change", "PreviewIds"),
        ("orders.place", "OrderIds"),
        ("orders.place_change", "OrderIds"),
        ("orders.cancel", "orderId"),
    ],
)
@pytest.mark.parametrize("value", [None, [], 0, -1, 1.5])
async def test_order_confirmation_ids_are_required(
    settings: ETradeSettings, auth: FakeAuthenticator, endpoint: str, field: str, value: object
) -> None:
    envelope = ENDPOINTS[endpoint][0]
    payload = {"messages": {"message": [{"description": "fake-sensitive-value"}]}, field: value}
    with pytest.raises(ETradeResponseError) as exc:
        await call_with_response(
            settings, auth, endpoint, httpx.Response(200, json={envelope: payload})
        )
    assert "fake-sensitive-value" not in str(exc.value)


@pytest.mark.parametrize(
    "endpoint",
    [
        "orders.preview",
        "orders.preview_change",
        "orders.place",
        "orders.place_change",
        "orders.cancel",
    ],
)
async def test_messages_alone_do_not_confirm_order_operations(
    settings: ETradeSettings, auth: FakeAuthenticator, endpoint: str
) -> None:
    envelope = ENDPOINTS[endpoint][0]
    with pytest.raises(ETradeResponseError):
        await call_with_response(
            settings,
            auth,
            endpoint,
            httpx.Response(200, json={envelope: {"messages": {"message": [{"code": 1}]}}}),
        )


@pytest.mark.parametrize(
    "endpoint, payload",
    [
        ("orders.preview", {"PreviewIds": [{"previewId": 1}]}),
        ("orders.place", {"orderId": 1}),
        ("orders.place", {"OrderIds": [{"orderId": 1}]}),
        ("orders.cancel", {"orderId": 1}),
    ],
)
async def test_minimal_order_confirmation_is_valid(
    settings: ETradeSettings, auth: FakeAuthenticator, endpoint: str, payload: dict[str, object]
) -> None:
    envelope = ENDPOINTS[endpoint][0]
    await call_with_response(
        settings, auth, endpoint, httpx.Response(200, json={envelope: payload})
    )


@pytest.mark.parametrize(
    "endpoint, payload",
    [
        ("orders.preview", {"PreviewIds": [{"previewId": True}]}),
        ("orders.preview", {"previewIds": {"PreviewId": [{"previewId": True}]}}),
        ("orders.place", {"orderId": True}),
        ("orders.place", {"OrderIds": [{"orderId": 1}, {"orderId": 0}]}),
        ("orders.place", {"OrderIds": [{"orderId": True}]}),
        ("orders.cancel", {"orderId": True}),
    ],
)
async def test_boolean_and_mixed_invalid_confirmation_ids_are_rejected(
    settings: ETradeSettings,
    auth: FakeAuthenticator,
    endpoint: str,
    payload: dict[str, object],
) -> None:
    envelope = ENDPOINTS[endpoint][0]
    with pytest.raises(ETradeResponseError):
        await call_with_response(
            settings, auth, endpoint, httpx.Response(200, json={envelope: payload})
        )


@pytest.mark.parametrize(
    "endpoint, payload",
    [
        ("portfolio.positions", {"totals": {"totalMarketValue": "1"}}),
        ("transactions.list", {"transactionCount": 0}),
        ("market.quotes", {"messages": {"message": [{"code": 1}]}}),
        ("market.chain", {"quoteType": "REALTIME"}),
        ("orders.list", {"marker": "next-marker"}),
        ("alerts.list", {"totalAlerts": 0}),
    ],
)
async def test_metadata_alone_does_not_establish_a_collection_response(
    settings: ETradeSettings,
    auth: FakeAuthenticator,
    endpoint: str,
    payload: dict[str, object],
) -> None:
    envelope = ENDPOINTS[endpoint][0]
    with pytest.raises(ETradeResponseError, match="missing collection"):
        await call_with_response(
            settings, auth, endpoint, httpx.Response(200, json={envelope: payload})
        )
