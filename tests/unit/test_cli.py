import asyncio
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from typer.testing import CliRunner

import etrade_python.cli.app as cli_app
from etrade_python import (
    Account,
    AccountBalanceRequest,
    AccountBalanceResponse,
    AccountListResponse,
    AlertDetailsRequest,
    AlertDetailsResponse,
    AlertsRequest,
    AlertsResponse,
    CancelOrderResponse,
    DeleteAlertsResponse,
    ETradeClient,
    ETradeCredentials,
    ETradeSettings,
    ETradeValidationError,
    OptionChainRequest,
    OptionChainResponse,
    OptionExpirationsRequest,
    OptionExpirationsResponse,
    OrdersRequest,
    OrdersResponse,
    PlaceOrderRequest,
    PlaceOrderResponse,
    PortfolioRequest,
    PortfolioResponse,
    PreviewOrderRequest,
    PreviewOrderResponse,
    ProductLookupResponse,
    Quote,
    QuotesRequest,
    QuotesResponse,
    TransactionDetailsRequest,
    TransactionDetailsResponse,
    TransactionsRequest,
    TransactionsResponse,
)
from etrade_python.auth import (
    AuthorizationUrl,
    MemoryCredentialStore,
    RequestToken,
    SessionManager,
    TokenStatus,
)
from etrade_python.cli.app import app

runner = CliRunner()


def _cli_private(name: str) -> Any:
    return getattr(cli_app, name)


class FakeOAuth:
    async def get_request_token(self) -> RequestToken:
        return RequestToken(
            oauth_token=SecretStr("fake-request-token"),
            oauth_token_secret=SecretStr("fake-secret"),
        )

    def get_authorization_url(self, request_token: RequestToken) -> AuthorizationUrl:
        return AuthorizationUrl(url="https://example.test/authorize", request_token=request_token)

    async def exchange_verifier(self, request_token: RequestToken, verifier: str) -> object:
        assert request_token.oauth_token.get_secret_value() == "fake-request-token"
        assert verifier == "fake-verifier"
        return object()

    async def revoke_access_token(self, credentials: object) -> object:
        return object()


class FakeSession:
    def __init__(self) -> None:
        self.saved = False
        self.deleted = False

    async def save(self, credentials: object) -> None:
        self.saved = True

    async def load(self) -> object | None:
        return None

    def status(self, credentials: object | None) -> TokenStatus:
        return TokenStatus.MISSING

    async def ensure_active(self) -> object:
        return object()

    async def delete(self) -> None:
        self.deleted = True


class FakeAccounts:
    def __init__(self, client: "FakeClient") -> None:
        self._client = client

    async def list(self) -> AccountListResponse:
        if self._client.profile == "error":
            raise ETradeValidationError("fake account failure")
        if self._client.profile == "empty-accounts":
            return AccountListResponse(accounts=[])
        return AccountListResponse(
            accounts=[
                Account(
                    accountId="123456",
                    accountIdKey="fake-account-key",
                    accountName="Individual Brokerage",
                    accountType="INDIVIDUAL",
                    accountStatus="ACTIVE",
                )
            ]
        )

    async def get_balance(
        self, account_id_key: str, request: AccountBalanceRequest | None = None
    ) -> AccountBalanceResponse:
        self._client.balance_account_id_key = account_id_key
        self._client.balance_request = request
        return AccountBalanceResponse.model_validate(
            {
                "accountId": "123456",
                "accountType": "INDIVIDUAL",
                "accountDescription": "Individual Brokerage",
                "computedBalance": {
                    "netCash": Decimal("10.25"),
                    "cashBalance": Decimal("20.50"),
                    "cashBuyingPower": Decimal("30.75"),
                },
                "cash": {"moneyMktBalance": Decimal("5.00")},
            }
        )


class FakePortfolio:
    def __init__(self, client: "FakeClient") -> None:
        self._client = client

    async def get_positions(
        self, account_id_key: str, request: PortfolioRequest | None = None
    ) -> PortfolioResponse:
        self._client.portfolio_account_id_key = account_id_key
        self._client.portfolio_request = request
        return PortfolioResponse.model_validate(
            {
                "Totals": {"totalMarketValue": Decimal("1000.00")},
                "AccountPortfolio": {
                    "accountId": "123456",
                    "Position": {
                        "positionId": 100,
                        "Product": {"symbol": "AAPL", "securityType": "EQ"},
                        "quantity": Decimal("2"),
                        "marketValue": Decimal("350.50"),
                    },
                },
            }
        )


class FakeTransactions:
    def __init__(self, client: "FakeClient") -> None:
        self._client = client

    async def list(
        self, account_id_key: str, request: TransactionsRequest | None = None
    ) -> TransactionsResponse:
        self._client.transactions_account_id_key = account_id_key
        self._client.transactions_request = request
        return TransactionsResponse.model_validate(
            {
                "Transaction": {
                    "transactionId": "99",
                    "transactionDate": 1767225600000,
                    "amount": Decimal("-12.34"),
                    "description": "BUY MSFT",
                    "transactionType": "Bought",
                },
                "pageMarkers": "88",
            }
        )

    async def get(
        self,
        account_id_key: str,
        transaction_id: str,
        request: TransactionDetailsRequest | None = None,
    ) -> TransactionDetailsResponse:
        self._client.transaction_detail_account_id_key = account_id_key
        self._client.transaction_id = transaction_id
        self._client.transaction_details_request = request
        return TransactionDetailsResponse.model_validate(
            {
                "transactionId": "99",
                "accountId": "123456",
                "amount": Decimal("-12.34"),
                "description": "BUY MSFT",
                "Brokerage": {
                    "Product": {"symbol": "MSFT", "securityType": "EQ"},
                    "quantity": Decimal("1"),
                    "price": Decimal("100.50"),
                },
            }
        )


class FakeMarket:
    def __init__(self, client: "FakeClient") -> None:
        self._client = client

    async def get_quote(self, symbol: str, request: QuotesRequest | None = None) -> Quote:
        self._client.market_quote_symbol = symbol
        self._client.market_quote_request = request
        return Quote.model_validate(
            {
                "Product": {"symbol": "GOOG", "securityType": "EQ"},
                "quoteStatus": "REALTIME",
                "All": {
                    "companyName": "Alphabet Inc.",
                    "lastTrade": Decimal("1175.74"),
                    "bid": Decimal("1175.00"),
                    "ask": Decimal("1176.00"),
                    "totalVolume": 12345,
                },
            }
        )

    async def get_quotes(
        self, symbols: list[str], request: QuotesRequest | None = None
    ) -> QuotesResponse:
        self._client.market_quotes_symbols = symbols
        self._client.market_quotes_request = request
        return QuotesResponse.model_validate(
            {
                "QuoteData": [
                    {
                        "Product": {"symbol": "GOOG", "securityType": "EQ"},
                        "All": {"lastTrade": Decimal("1175.74")},
                    },
                    {
                        "Product": {"symbol": "AAPL", "securityType": "EQ"},
                        "All": {"lastTrade": Decimal("200.01")},
                    },
                ]
            }
        )

    async def lookup_product(self, search: str) -> ProductLookupResponse:
        self._client.market_lookup_search = search
        return ProductLookupResponse.model_validate(
            {
                "Data": {
                    "symbol": "A",
                    "description": "Agilent Technologies Inc.",
                    "type": "EQ",
                }
            }
        )

    async def get_option_expirations(
        self, symbol: str, request: OptionExpirationsRequest | None = None
    ) -> OptionExpirationsResponse:
        self._client.market_option_expirations_symbol = symbol
        self._client.market_option_expirations_request = request
        if self._client.profile == "empty-expirations":
            return OptionExpirationsResponse.model_validate({"ExpirationDate": []})
        if self._client.profile == "weekly-expirations":
            return OptionExpirationsResponse.model_validate(
                {
                    "ExpirationDate": [
                        {"year": 2026, "month": 10, "day": 9, "expiryType": "WEEKLY"},
                        {"year": 2026, "month": 10, "day": 23, "expiryType": "WEEKLY"},
                    ]
                }
            )
        return OptionExpirationsResponse.model_validate(
            {"ExpirationDate": {"year": 2026, "month": 10, "day": 16, "expiryType": "MONTHLY"}}
        )

    async def get_option_chain(
        self, symbol: str, request: OptionChainRequest | None = None
    ) -> OptionChainResponse:
        self._client.market_option_chain_symbol = symbol
        self._client.market_option_chain_request = request
        if self._client.profile == "empty-chain":
            return OptionChainResponse.model_validate(
                {"quoteType": "DELAYED", "nearPrice": Decimal("200"), "OptionPair": []}
            )
        pairs: list[dict[str, object]] = []
        for strike in [175, 180, 190, 195, 200, 210, 215]:
            strike_decimal = Decimal(str(strike))
            pairs.append(
                {
                    "Call": {
                        "displaySymbol": f"AAPL Oct 16 '26 ${strike} Call",
                        "strikePrice": strike_decimal,
                        "bid": Decimal(str(strike / 100)),
                        "ask": Decimal(str(strike / 100 + 0.20)),
                    },
                    "Put": {
                        "displaySymbol": f"AAPL Oct 16 '26 ${strike} Put",
                        "strikePrice": strike_decimal,
                        "bid": Decimal(str((220 - strike) / 100)),
                        "ask": Decimal(str((220 - strike) / 100 + 0.15)),
                    },
                }
            )
        return OptionChainResponse.model_validate(
            {"quoteType": "DELAYED", "nearPrice": Decimal("200"), "OptionPair": pairs}
        )


class FakeOrders:
    def __init__(self, client: "FakeClient") -> None:
        self._client = client

    async def list(
        self, account_id_key: str, request: OrdersRequest | None = None
    ) -> OrdersResponse:
        self._client.orders_account_id_key = account_id_key
        self._client.orders_request = request
        if self._client.profile == "empty-orders":
            return OrdersResponse(order=[])
        return OrdersResponse.model_validate(
            {
                "Order": {
                    "orderId": 96,
                    "orderType": "EQ",
                    "totalOrderValue": Decimal("100.00"),
                    "OrderDetail": {
                        "status": "OPEN",
                        "priceType": "LIMIT",
                        "orderTerm": "GOOD_FOR_DAY",
                        "Instrument": {
                            "Product": {"symbol": "AAPL", "securityType": "EQ"},
                            "orderAction": "BUY",
                            "quantity": Decimal("1"),
                        },
                    },
                }
            }
        )

    async def preview(
        self, account_id_key: str, request: PreviewOrderRequest
    ) -> PreviewOrderResponse:
        self._client.order_preview_account_id_key = account_id_key
        self._client.order_preview_request = request
        if self._client.profile == "no-preview-ids":
            return PreviewOrderResponse.model_validate(
                {
                    "orderType": "EQ",
                    "totalOrderValue": Decimal("100.00"),
                    "PreviewIds": [],
                    "Order": {"priceType": "LIMIT", "limitPrice": Decimal("100.00")},
                }
            )
        return PreviewOrderResponse.model_validate(
            {
                "orderType": "EQ",
                "totalOrderValue": Decimal("100.00"),
                "PreviewIds": {"previewId": 123},
                "Order": {"priceType": "LIMIT", "limitPrice": Decimal("100.00")},
            }
        )

    async def place(self, account_id_key: str, request: PlaceOrderRequest) -> PlaceOrderResponse:
        self._client.order_place_account_id_key = account_id_key
        self._client.order_place_request = request
        return PlaceOrderResponse.model_validate(
            {"orderType": "EQ", "OrderIds": {"orderId": 456}, "Order": {"priceType": "LIMIT"}}
        )

    async def preview_change(
        self, account_id_key: str, order_id: int, request: PreviewOrderRequest
    ) -> PreviewOrderResponse:
        self._client.order_preview_change_account_id_key = account_id_key
        self._client.order_preview_change_order_id = order_id
        self._client.order_preview_change_request = request
        return await self.preview(account_id_key, request)

    async def place_change(
        self, account_id_key: str, order_id: int, request: PlaceOrderRequest
    ) -> PlaceOrderResponse:
        self._client.order_place_change_account_id_key = account_id_key
        self._client.order_place_change_order_id = order_id
        self._client.order_place_change_request = request
        return PlaceOrderResponse.model_validate(
            {"orderType": "EQ", "OrderIds": {"orderId": 789}, "Order": {"priceType": "LIMIT"}}
        )

    async def cancel(self, account_id_key: str, order_id: int) -> CancelOrderResponse:
        self._client.order_cancel_account_id_key = account_id_key
        self._client.order_cancel_order_id = order_id
        return CancelOrderResponse.model_validate(
            {
                "accountId": "123456",
                "orderId": order_id,
                "Messages": {"Message": {"description": "Cancel requested", "code": 5011}},
            }
        )


class FakeAlerts:
    def __init__(self, client: "FakeClient") -> None:
        self._client = client

    async def list(self, request: AlertsRequest | None = None) -> AlertsResponse:
        self._client.alerts_request = request
        if self._client.profile == "empty-alerts":
            return AlertsResponse(totalAlerts=0, alerts=[])
        return AlertsResponse.model_validate(
            {
                "totalAlerts": 2,
                "Alert": [
                    {
                        "id": 6774,
                        "createTime": 1529426402,
                        "subject": "Transfer failed-Insufficient Funds",
                        "status": "UNREAD",
                    },
                    {
                        "id": 6773,
                        "createTime": 1529416825,
                        "subject": "AAPL down by at least 2.00%",
                        "status": "UNREAD",
                    },
                ],
            }
        )

    async def get(
        self, alert_id: int, request: AlertDetailsRequest | None = None
    ) -> AlertDetailsResponse:
        self._client.alert_id = alert_id
        self._client.alert_details_request = request
        return AlertDetailsResponse.model_validate(
            {
                "id": alert_id,
                "createTime": 1529416825,
                "subject": "AAPL down by at least 2.00%",
                "symbol": "AAPL",
                "msgText": "APPLE INC COM (AAPL) stock has met your target.",
                "readTime": 0,
                "deleteTime": 0,
            }
        )

    async def delete(self, alert_ids: Sequence[int] | int) -> DeleteAlertsResponse:
        self._client.alert_delete_ids = alert_ids
        return DeleteAlertsResponse(result="SUCCESS")


class FakeClient:
    instances: list["FakeClient"] = []

    def __init__(self, settings: object, *, profile: str) -> None:
        self.oauth = FakeOAuth()
        self.session = FakeSession()
        self.accounts = FakeAccounts(self)
        self.portfolio = FakePortfolio(self)
        self.transactions = FakeTransactions(self)
        self.alerts = FakeAlerts(self)
        self.market = FakeMarket(self)
        self.orders = FakeOrders(self)
        self.profile = profile
        self.balance_account_id_key: str | None = None
        self.balance_request: AccountBalanceRequest | None = None
        self.portfolio_account_id_key: str | None = None
        self.portfolio_request: PortfolioRequest | None = None
        self.transactions_account_id_key: str | None = None
        self.transactions_request: TransactionsRequest | None = None
        self.transaction_detail_account_id_key: str | None = None
        self.transaction_id: str | None = None
        self.transaction_details_request: TransactionDetailsRequest | None = None
        self.alerts_request: AlertsRequest | None = None
        self.alert_id: int | None = None
        self.alert_details_request: AlertDetailsRequest | None = None
        self.alert_delete_ids: Sequence[int] | int | None = None
        self.market_quote_symbol: str | None = None
        self.market_quote_request: QuotesRequest | None = None
        self.market_quotes_symbols: list[str] | None = None
        self.market_quotes_request: QuotesRequest | None = None
        self.market_lookup_search: str | None = None
        self.market_option_expirations_symbol: str | None = None
        self.market_option_expirations_request: OptionExpirationsRequest | None = None
        self.market_option_chain_symbol: str | None = None
        self.market_option_chain_request: OptionChainRequest | None = None
        self.orders_account_id_key: str | None = None
        self.orders_request: OrdersRequest | None = None
        self.order_preview_account_id_key: str | None = None
        self.order_preview_request: PreviewOrderRequest | None = None
        self.order_place_account_id_key: str | None = None
        self.order_place_request: PlaceOrderRequest | None = None
        self.order_preview_change_account_id_key: str | None = None
        self.order_preview_change_order_id: int | None = None
        self.order_preview_change_request: PreviewOrderRequest | None = None
        self.order_place_change_account_id_key: str | None = None
        self.order_place_change_order_id: int | None = None
        self.order_place_change_request: PlaceOrderRequest | None = None
        self.order_cancel_account_id_key: str | None = None
        self.order_cancel_order_id: int | None = None
        self.__class__.instances.append(self)

    async def __aenter__(self) -> "FakeClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


@pytest.fixture(autouse=True)
def cli_date(monkeypatch: pytest.MonkeyPatch) -> Callable[[date], None]:
    """Keep expiration fixtures independent of the date the suite is run."""
    current_date = date(2026, 10, 1)

    class FixedDate(date):
        @classmethod
        def today(cls) -> "FixedDate":
            return cls(current_date.year, current_date.month, current_date.day)

    def set_date(value: date) -> None:
        nonlocal current_date
        current_date = value

    monkeypatch.setattr(cli_app, "date", FixedDate)
    return set_date


@pytest.fixture(autouse=True)
def reset_fake_client() -> None:
    FakeClient.instances = []


def set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETRADE_CONSUMER_KEY", "fake-key")
    monkeypatch.setenv("ETRADE_CONSUMER_SECRET", "fake-secret")


def test_cli_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0.dev0" in result.output


def test_auth_status(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["auth", "status"])

    assert result.exit_code == 0
    assert "No credentials stored" in result.output
    assert "fake-key" not in result.output


def test_auth_login_does_not_echo_verifier(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["auth", "login"], input="fake-verifier\n")

    assert result.exit_code == 0
    assert "https://example.test/authorize" in result.output
    assert "Credentials saved" in result.output
    assert "fake-verifier" not in result.output


def test_auth_revoke_redirect_preserves_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    credentials = ETradeCredentials(
        access_token=SecretStr("fake-access-token"),
        access_token_secret=SecretStr("fake-access-secret"),
    )
    store = MemoryCredentialStore()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(302, headers={"Location": "https://example.invalid/"})

    def make_client(settings: ETradeSettings, *, profile: str) -> ETradeClient:
        return ETradeClient(
            settings,
            profile=profile,
            credential_store=store,
            http_transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(cli_app, "ETradeClient", make_client)

    async def stored_credentials(*, save: bool = False) -> ETradeCredentials | None:
        async with make_client(ETradeSettings(), profile="default") as client:
            if save:
                await client.session.save(credentials)
            return await client.session.load()

    asyncio.run(stored_credentials(save=True))
    result = runner.invoke(app, ["auth", "revoke"])

    assert result.exit_code == 1
    assert "HTTP 302" in result.output
    assert "Credentials removed" not in result.output
    assert asyncio.run(stored_credentials()) == credentials
    assert len(seen) == 1
    assert seen[0].url.path == "/oauth/revoke_access_token"


@pytest.mark.parametrize("status_code", [200, 302, 401, 500])
def test_auth_renew_contacts_broker(monkeypatch: pytest.MonkeyPatch, status_code: int) -> None:
    set_env(monkeypatch)
    now = datetime(2026, 9, 26, 18, tzinfo=UTC)
    credentials = ETradeCredentials(
        access_token=SecretStr("fake-access-token"),
        access_token_secret=SecretStr("fake-access-secret"),
        acquired_at=now - timedelta(hours=1),
        last_used_at=now - timedelta(minutes=1),
    )
    store = MemoryCredentialStore()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status_code, text="Access Token has been renewed")

    def make_client(settings: ETradeSettings, *, profile: str) -> ETradeClient:
        client = ETradeClient(
            settings,
            profile=profile,
            credential_store=store,
            http_transport=httpx.MockTransport(handler),
        )
        client.session = SessionManager(
            settings=settings,
            oauth_client=client.oauth,
            credential_store=store,
            profile=profile,
            clock=lambda: now,
        )
        return client

    async def stored_credentials(*, save: bool = False) -> ETradeCredentials | None:
        async with make_client(ETradeSettings(), profile="manual") as client:
            if save:
                await client.session.save(credentials)
            return await client.session.load()

    monkeypatch.setattr(cli_app, "ETradeClient", make_client)
    asyncio.run(stored_credentials(save=True))
    result = runner.invoke(app, ["auth", "renew", "--profile", "manual"])

    assert len(seen) == 1
    assert seen[0].url.path == "/oauth/renew_access_token"
    saved = asyncio.run(stored_credentials())
    if status_code == 200:
        assert result.exit_code == 0
        assert "Credentials renewed for profile 'manual'." in result.output
        assert saved is not None
        assert saved.last_used_at == now
        assert saved.renewed_at == now
    else:
        assert result.exit_code == 1
        assert f"HTTP {status_code}" in result.output
        assert "Credentials renewed" not in result.output
        assert saved == credentials


def test_accounts_list_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["accounts", "list", "--profile", "manual"])

    assert result.exit_code == 0
    assert "Individual Brokerage" in result.output
    assert "Account ID: 123456" in result.output
    assert "Account ID key: fake-account-key" in result.output
    assert "Status: ACTIVE" in result.output
    assert FakeClient.instances[0].profile == "manual"


def test_accounts_list_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["accounts", "list", "--json"])

    assert result.exit_code == 0
    assert '"accounts": [' in result.output
    assert '"accountId": "123456"' in result.output
    assert '"accountIdKey": "fake-account-key"' in result.output


def test_accounts_balance_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        [
            "accounts",
            "balance",
            "fake-account-key",
            "--account-type",
            "CASH",
            "--real-time-nav",
        ],
    )

    assert result.exit_code == 0
    assert "Account ID: 123456" in result.output
    assert "Net cash: 10.25" in result.output
    assert "Cash buying power: 30.75" in result.output
    client = FakeClient.instances[0]
    assert client.balance_account_id_key == "fake-account-key"
    assert client.balance_request == AccountBalanceRequest(account_type="CASH", real_time_nav=True)


def test_accounts_balance_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["accounts", "balance", "fake-account-key", "--json"])

    assert result.exit_code == 0
    assert '"accountId": "123456"' in result.output
    assert '"netCash": "10.25"' in result.output


def test_accounts_errors_exit_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["accounts", "list", "--profile", "error"])

    assert result.exit_code == 1
    assert "fake account failure" in result.output
    assert "fake-key" not in result.output


def test_portfolio_positions_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        [
            "portfolio",
            "positions",
            "fake-account-key",
            "--count",
            "10",
            "--view",
            "QUICK",
            "--lots-required",
            "--totals-required",
        ],
    )

    assert result.exit_code == 0
    assert "Total market value: 1000.00" in result.output
    assert "AAPL" in result.output
    assert "Market value: 350.50" in result.output
    client = FakeClient.instances[0]
    assert client.portfolio_account_id_key == "fake-account-key"
    assert client.portfolio_request == PortfolioRequest(
        count=10, view="QUICK", lots_required=True, totals_required=True
    )


def test_portfolio_positions_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["portfolio", "positions", "fake-account-key", "--json"])

    assert result.exit_code == 0
    assert '"accountPortfolio": [' in result.output
    assert '"symbol": "AAPL"' in result.output


def test_transactions_list_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        [
            "transactions",
            "list",
            "fake-account-key",
            "--count",
            "10",
            "--start-date",
            "01012026",
            "--end-date",
            "01312026",
        ],
    )

    assert result.exit_code == 0
    assert "BUY MSFT" in result.output
    assert "Transaction ID: 99" in result.output
    assert "Amount: -12.34" in result.output
    client = FakeClient.instances[0]
    assert client.transactions_account_id_key == "fake-account-key"
    assert client.transactions_request == TransactionsRequest(
        count=10, start_date="01012026", end_date="01312026"
    )


@pytest.mark.parametrize("sort_order", [None, "ASC"])
def test_transactions_list_cli_sort_order(
    monkeypatch: pytest.MonkeyPatch, sort_order: str | None
) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)
    args = ["transactions", "list", "fake-account-key"]
    if sort_order is not None:
        args.extend(["--sort-order", sort_order])

    result = runner.invoke(app, args)

    assert result.exit_code == 0
    request = FakeClient.instances[0].transactions_request
    assert request is not None
    assert request.sort_order == (sort_order or "DESC")


def test_transactions_list_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["transactions", "list", "fake-account-key", "--json"])

    assert result.exit_code == 0
    assert '"transaction": [' in result.output
    assert '"transactionId": "99"' in result.output


def test_transaction_get_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        ["transactions", "get", "fake-account-key", "99", "--store-id", "bank"],
    )

    assert result.exit_code == 0
    assert "BUY MSFT" in result.output
    assert "Symbol: MSFT" in result.output
    client = FakeClient.instances[0]
    assert client.transaction_detail_account_id_key == "fake-account-key"
    assert client.transaction_id == "99"
    assert client.transaction_details_request == TransactionDetailsRequest(store_id="bank")


def test_transaction_get_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["transactions", "get", "fake-account-key", "99", "--json"])

    assert result.exit_code == 0
    assert '"transactionId": "99"' in result.output
    assert '"symbol": "MSFT"' in result.output


def test_alerts_list_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        [
            "alerts",
            "list",
            "--count",
            "10",
            "--category",
            "stock",
            "--status",
            "unread",
            "--direction",
            "desc",
            "--search",
            "AAPL",
        ],
    )

    assert result.exit_code == 0
    assert "Total alerts: 2" in result.output
    assert "Transfer failed-Insufficient Funds" in result.output
    client = FakeClient.instances[0]
    assert client.alerts_request == AlertsRequest(
        count=10, category="STOCK", status="UNREAD", direction="DESC", search="AAPL"
    )


def test_alerts_list_empty_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["alerts", "list", "--profile", "empty-alerts"])

    assert result.exit_code == 0
    assert "No alerts found." in result.output


def test_alerts_list_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["alerts", "list", "--json"])

    assert result.exit_code == 0
    assert '"totalAlerts": 2' in result.output
    assert '"subject": "AAPL down by at least 2.00%"' in result.output


def test_alert_get_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["alerts", "get", "6773", "--html-tags"])

    assert result.exit_code == 0
    assert "AAPL down by at least 2.00%" in result.output
    assert "Symbol: AAPL" in result.output
    client = FakeClient.instances[0]
    assert client.alert_id == 6773
    assert client.alert_details_request == AlertDetailsRequest(htmlTags=True)


def test_alert_delete_requires_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["alerts", "delete", "6772"])

    assert result.exit_code == 1
    assert "Refusing to delete alerts without --confirm-delete." in result.output
    assert FakeClient.instances == []


def test_alert_delete_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["alerts", "delete", "6772", "6774", "--confirm-delete"])

    assert result.exit_code == 0
    assert "Result: SUCCESS" in result.output
    assert FakeClient.instances[0].alert_delete_ids == [6772, 6774]


def test_market_quote_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        [
            "market",
            "quote",
            "goog",
            "--detail-flag",
            "all",
            "--require-earnings-date",
        ],
    )

    assert result.exit_code == 0
    assert "GOOG" in result.output
    assert "Company: Alphabet Inc." in result.output
    assert "Last trade: 1175.74" in result.output
    client = FakeClient.instances[0]
    assert client.market_quote_symbol == "goog"
    assert client.market_quote_request == QuotesRequest(
        detail_flag="ALL", require_earnings_date=True
    )


def test_market_quote_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["market", "quote", "GOOG", "--json"])

    assert result.exit_code == 0
    assert '"symbol": "GOOG"' in result.output
    assert '"lastTrade": "1175.74"' in result.output


def test_market_quotes_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        ["market", "quotes", "GOOG", "AAPL", "--override-symbol-count"],
    )

    assert result.exit_code == 0
    assert "GOOG" in result.output
    assert "AAPL" in result.output
    client = FakeClient.instances[0]
    assert client.market_quotes_symbols == ["GOOG", "AAPL"]
    assert client.market_quotes_request == QuotesRequest(override_symbol_count=True)


@pytest.mark.parametrize("search", ["agilent", "Bank of America"])
def test_market_lookup_human_output(monkeypatch: pytest.MonkeyPatch, search: str) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["market", "lookup", search])

    assert result.exit_code == 0
    assert "A" in result.output
    assert "Agilent Technologies Inc." in result.output
    assert FakeClient.instances[0].market_lookup_search == search


def test_market_option_expirations_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app, ["market", "option-expirations", "AAPL", "--expiry-type", "monthly"]
    )

    assert result.exit_code == 0
    assert "2026-10-16" in result.output
    assert "Type: MONTHLY" in result.output
    client = FakeClient.instances[0]
    assert client.market_option_expirations_symbol == "AAPL"
    assert client.market_option_expirations_request == OptionExpirationsRequest(
        expiry_type="MONTHLY"
    )


def test_market_option_chain_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        [
            "market",
            "option-chain",
            "AAPL",
            "--expiry-year",
            "2026",
            "--expiry-month",
            "10",
            "--expiry-day",
            "16",
            "--chain-type",
            "callput",
            "--include-weekly",
        ],
    )

    assert result.exit_code == 0
    assert "Quote type: DELAYED" in result.output
    assert "AAPL Oct 16 '26 $200 Call" in result.output
    assert "Ask: 2.2" in result.output
    assert "AAPL Oct 16 '26 $200 Put" in result.output
    client = FakeClient.instances[0]
    assert client.market_option_chain_symbol == "AAPL"
    assert client.market_option_chain_request == OptionChainRequest(
        expiry_year=2026,
        expiry_month=10,
        expiry_day=16,
        chain_type="CALLPUT",
        include_weekly=True,
    )


def _write_preview_order_file(tmp_path: Path) -> str:
    path = tmp_path / "preview.json"
    path.write_text(
        '{"PreviewOrderRequest":{"orderType":"EQ","clientOrderId":"abc123","Order":[{"priceType":"LIMIT","orderTerm":"GOOD_FOR_DAY","limitPrice":"100","Instrument":[{"Product":{"symbol":"AAPL","securityType":"EQ"},"orderAction":"BUY","quantity":"1"}]}]}}'
    )
    return str(path)


def _write_place_order_file(tmp_path: Path) -> str:
    path = tmp_path / "place.json"
    path.write_text(
        '{"PlaceOrderRequest":{"orderType":"EQ","clientOrderId":"abc123","PreviewIds":[{"previewId":123}],"Order":[{"priceType":"LIMIT","orderTerm":"GOOD_FOR_DAY","limitPrice":"100","Instrument":[{"Product":{"symbol":"AAPL","securityType":"EQ"},"orderAction":"BUY","quantity":"1"}]}]}}'
    )
    return str(path)


def test_orders_list_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app, ["orders", "list", "fake-account-key", "--count", "10", "--status", "OPEN"]
    )

    assert result.exit_code == 0
    assert "Order ID: 96" in result.output
    assert "Symbol: AAPL" in result.output
    client = FakeClient.instances[0]
    assert client.orders_account_id_key == "fake-account-key"
    assert client.orders_request == OrdersRequest(count=10, status="OPEN")


def test_orders_preview_reads_request_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)
    path = _write_preview_order_file(tmp_path)

    result = runner.invoke(app, ["orders", "preview", "fake-account-key", path])

    assert result.exit_code == 0
    assert "Preview IDs: 123" in result.output
    client = FakeClient.instances[0]
    assert client.order_preview_account_id_key == "fake-account-key"
    assert client.order_preview_request is not None
    assert client.order_preview_request.client_order_id == "abc123"


def test_orders_place_requires_confirmation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)
    path = _write_place_order_file(tmp_path)

    result = runner.invoke(app, ["orders", "place", "fake-account-key", path])

    assert result.exit_code == 1
    assert "require --confirm-live-order" in result.output
    assert FakeClient.instances == []


def test_orders_place_with_confirmation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)
    path = _write_place_order_file(tmp_path)

    result = runner.invoke(
        app, ["orders", "place", "fake-account-key", path, "--confirm-live-order"]
    )

    assert result.exit_code == 0
    assert "Order IDs: 456" in result.output
    client = FakeClient.instances[0]
    assert client.order_place_account_id_key == "fake-account-key"
    assert client.order_place_request is not None
    assert client.order_place_request.preview_ids[0].preview_id == 123


def test_orders_cancel_requires_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["orders", "cancel", "fake-account-key", "456"])

    assert result.exit_code == 1
    assert "require --confirm-live-order" in result.output
    assert FakeClient.instances == []


def test_orders_cancel_with_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app, ["orders", "cancel", "fake-account-key", "456", "--confirm-live-order"]
    )

    assert result.exit_code == 0
    assert "Cancel requested" in result.output
    client = FakeClient.instances[0]
    assert client.order_cancel_account_id_key == "fake-account-key"
    assert client.order_cancel_order_id == 456


def test_orders_list_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["orders", "list", "fake-account-key", "--json"])

    assert result.exit_code == 0
    assert '"orderId": 96' in result.output
    assert '"symbol": "AAPL"' in result.output


def test_orders_list_empty_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["orders", "list", "fake-account-key", "--profile", "empty-orders"])

    assert result.exit_code == 0
    assert "No orders found." in result.output


def test_orders_preview_json_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)
    path = _write_preview_order_file(tmp_path)

    result = runner.invoke(app, ["orders", "preview", "fake-account-key", path, "--json"])

    assert result.exit_code == 0
    assert '"previewId": 123' in result.output
    assert '"totalOrderValue": "100.00"' in result.output


def test_orders_preview_change_reads_request_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)
    path = _write_preview_order_file(tmp_path)

    result = runner.invoke(app, ["orders", "preview-change", "fake-account-key", "456", path])

    assert result.exit_code == 0
    client = FakeClient.instances[0]
    assert client.order_preview_change_account_id_key == "fake-account-key"
    assert client.order_preview_change_order_id == 456
    assert client.order_preview_change_request is not None


def test_orders_place_change_with_confirmation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)
    path = _write_place_order_file(tmp_path)

    result = runner.invoke(
        app,
        [
            "orders",
            "place-change",
            "fake-account-key",
            "456",
            path,
            "--confirm-live-order",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert '"orderId": 789' in result.output
    client = FakeClient.instances[0]
    assert client.order_place_change_account_id_key == "fake-account-key"
    assert client.order_place_change_order_id == 456
    assert client.order_place_change_request is not None


def test_orders_place_change_requires_confirmation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)
    path = _write_place_order_file(tmp_path)

    result = runner.invoke(app, ["orders", "place-change", "fake-account-key", "456", path])

    assert result.exit_code == 1
    assert "require --confirm-live-order" in result.output
    assert FakeClient.instances == []


def test_orders_demo_help() -> None:
    result = runner.invoke(app, ["orders", "demo", "--help"])

    assert result.exit_code == 0
    assert "Run an interactive order preview/place/change/cancel demo" in result.output


@pytest.mark.parametrize(
    ("count", "monthly_index", "menu_input", "selected_day", "expected_pages"),
    [
        (25, 11, "\n", 12, [2]),
        (25, None, "n\nn\n25\n", 25, [1, 2, 3]),
        (25, 11, "p\n\n", 1, [2, 1]),
        (25, 11, "n\n\n", 21, [2, 3]),
        (25, 11, "n\np\n\n", 12, [2, 3, 2]),
        (25, None, "p\n11\nx\nN\nn\nn\nP\n11\n", 11, [1, 1, 1, 1, 2, 3, 3, 2]),
        (20, 19, "\n", 20, [2]),
        (10, 8, "\n", 9, [1]),
        (3, None, "\n", 1, [1]),
        (3, 1, "3\n", 3, [1]),
        (1, None, "\n", 1, [1]),
    ],
)
def test_expiration_menu_pagination(
    count: int,
    monthly_index: int | None,
    menu_input: str,
    selected_day: int,
    expected_pages: list[int],
) -> None:
    expirations = [
        cli_app.OptionExpiration(
            year=2026,
            month=11,
            day=index + 1,
            expiryType="MONTHLY" if index == monthly_index else "WEEKLY",
        )
        for index in range(count)
    ]
    menu = cli_app.typer.Typer()

    @menu.command()
    def choose() -> None:
        selected = _cli_private("_prompt_expiration_choice")(expirations)
        cli_app.typer.echo(f"Selected: {selected.isoformat()}")

    result = runner.invoke(menu, input=menu_input)

    assert result.exit_code == 0
    assert f"Selected: 2026-11-{selected_day:02d}" in result.output
    pages = result.output.split("Available expirations (Page ")[1:]
    assert len(pages) == len(expected_pages)
    total_pages = (count + 9) // 10
    for page_output, page_number in zip(pages, expected_pages, strict=True):
        assert page_output.startswith(f"{page_number} of {total_pages}):")
        start = (page_number - 1) * 10
        end = min(start + 10, count)
        default_index = monthly_index if monthly_index is not None else 0
        visible_default = default_index if start <= default_index < end else start
        for index in range(count):
            label = f"  {index + 1}. 2026-11-{index + 1:02d}"
            assert (label in page_output) == (start <= index < end)
        expiry_type = "MONTHLY" if visible_default == monthly_index else "WEEKLY"
        assert (
            f"  {visible_default + 1}. 2026-11-{visible_default + 1:02d} {expiry_type} [default]"
            in page_output
        )
        assert f"Expiration [{visible_default + 1}]:" in page_output
        assert ("n. Next page" in page_output) == (page_number < total_pages)
        assert ("p. Previous page" in page_output) == (page_number > 1)


@pytest.mark.parametrize(
    "today, expected",
    [
        (date(2026, 10, 1), date(2026, 10, 16)),
        (date(2026, 10, 16), date(2026, 10, 16)),
        (date(2026, 10, 17), date(2026, 11, 20)),
        (date(2026, 12, 19), date(2027, 1, 15)),
    ],
)
def test_next_third_friday_uses_fixed_date(
    cli_date: Callable[[date], None], today: date, expected: date
) -> None:
    cli_date(today)
    assert _cli_private("_next_third_friday")() == expected


@pytest.mark.parametrize(
    "today, expected_days",
    [
        (date(2026, 10, 8), [9, 23]),
        (date(2026, 10, 9), [9, 23]),
        (date(2026, 10, 10), [23]),
        (date(2026, 10, 24), []),
    ],
)
async def test_option_expiration_filtering_uses_fixed_date(
    monkeypatch: pytest.MonkeyPatch,
    cli_date: Callable[[date], None],
    today: date,
    expected_days: list[int],
) -> None:
    set_env(monkeypatch)
    cli_date(today)
    client = FakeClient(ETradeSettings(), profile="weekly-expirations")
    expirations = await _cli_private("_get_option_expirations")(client, "AAPL")
    assert [expiration.day for expiration in expirations] == expected_days


def test_orders_demo_helper_fallbacks() -> None:
    third_friday = _cli_private("_third_friday")
    expiration_date = _cli_private("_expiration_date")
    default_expiration_index = _cli_private("_default_expiration_index")
    add = _cli_private("_add")
    subtract = _cli_private("_subtract")
    format_decimal = _cli_private("_format_decimal")
    option_side = _cli_private("_option_side")

    assert third_friday(2026, 10) == date(2026, 10, 16)
    assert expiration_date(cli_app.OptionExpiration()) is None
    assert (
        default_expiration_index(
            [
                cli_app.OptionExpiration(year=2026, month=10, day=9, expiryType="WEEKLY"),
                cli_app.OptionExpiration(year=2026, month=10, day=16, expiryType="MONTHLY"),
            ]
        )
        == 1
    )
    assert add(Decimal("1"), None) is None
    assert subtract(None, Decimal("1")) is None
    assert format_decimal(None) is None
    assert format_decimal(Decimal("100.00")) == "100"
    assert option_side("long-put") == "PUT"
    assert option_side("long-call") == "CALL"


def test_orders_demo_quote_and_contract_helpers() -> None:
    chain = OptionChainResponse.model_validate(
        {
            "OptionPair": {
                "Call": {
                    "strikePrice": Decimal("200"),
                    "bid": Decimal("3.20"),
                    "ask": Decimal("3.40"),
                },
                "Put": {
                    "strikePrice": Decimal("200"),
                    "bid": Decimal("2.10"),
                    "ask": Decimal("2.25"),
                },
            }
        }
    )
    quote = Quote.model_validate(
        {
            "Product": {"symbol": "AAPL", "securityType": "EQ"},
            "All": {"ask": Decimal("200.00")},
        }
    )

    find_option_contract = _cli_private("_find_option_contract")
    option_contracts = _cli_private("_option_contracts")
    visible_option_contracts = _cli_private("_visible_option_contracts")
    default_contract_index = _cli_private("_default_contract_index")
    contract_ask = _cli_private("_contract_ask")
    contract_bid = _cli_private("_contract_bid")
    quote_ask = _cli_private("_quote_ask")
    is_covered_call_ratio = _cli_private("_is_covered_call_ratio")
    buy_write_estimate = _cli_private("_buy_write_estimate")

    contracts = option_contracts(chain, "CALL")
    assert [contract.strike_price for contract in contracts] == [Decimal("200")]
    assert option_contracts(None, "CALL") == []
    assert visible_option_contracts(contracts, Decimal("200")) == contracts
    assert default_contract_index([], Decimal("200")) == 0
    assert default_contract_index(contracts, None) == 0
    assert default_contract_index(contracts, Decimal("201")) == 0
    assert contract_ask(find_option_contract(chain, "CALL", Decimal("200"))) == Decimal("3.40")
    assert contract_bid(None) is None
    assert contract_ask(None) is None
    assert find_option_contract(None, "CALL", Decimal("200")) is None
    assert find_option_contract(chain, "CALL", Decimal("201")) is None
    assert quote_ask(quote) == Decimal("200.00")
    assert (
        quote_ask(Quote.model_validate({"Product": {"symbol": "AAPL", "securityType": "EQ"}}))
        is None
    )
    assert quote_ask(None) is None
    assert (
        buy_write_estimate(None, Decimal("100"), chain.option_pairs[0].call, Decimal("1")) is None
    )
    assert is_covered_call_ratio(Decimal("100"), Decimal("1")) is True
    assert is_covered_call_ratio(Decimal("100"), Decimal("2")) is False
    assert buy_write_estimate(
        quote, Decimal("100"), chain.option_pairs[0].call, Decimal("1")
    ) == Decimal("196.80")
    assert buy_write_estimate(
        quote, Decimal("200"), chain.option_pairs[0].call, Decimal("2")
    ) == Decimal("196.80")


def test_orders_demo_option_contracts_are_sorted_and_deduplicated() -> None:
    chain = OptionChainResponse.model_validate(
        {
            "nearPrice": Decimal("207"),
            "OptionPair": [
                {"Call": {"strikePrice": Decimal("210"), "bid": Decimal("1")}},
                {"Call": {"bid": Decimal("0")}},
                {"Call": {"strikePrice": Decimal("200"), "bid": Decimal("2")}},
                {"Call": {"strikePrice": Decimal("200"), "bid": Decimal("9")}},
            ],
        }
    )
    option_contracts = _cli_private("_option_contracts")
    default_contract_index = _cli_private("_default_contract_index")

    contracts = option_contracts(chain, "CALL")

    assert [contract.strike_price for contract in contracts] == [Decimal("200"), Decimal("210")]
    assert contracts[0].bid == Decimal("2")
    assert default_contract_index(contracts, chain.near_price) == 1


def test_orders_demo_visible_option_contracts_window_around_near_price() -> None:
    contracts = [
        cli_app.OptionContract(strikePrice=Decimal(str(strike))) for strike in range(250, 370, 5)
    ]
    visible_option_contracts = _cli_private("_visible_option_contracts")

    visible = visible_option_contracts(contracts, Decimal("300"))

    assert [contract.strike_price for contract in visible] == [
        Decimal("275"),
        Decimal("280"),
        Decimal("285"),
        Decimal("290"),
        Decimal("295"),
        Decimal("300"),
        Decimal("305"),
        Decimal("310"),
        Decimal("315"),
        Decimal("320"),
        Decimal("325"),
    ]


def test_orders_demo_visible_option_contracts_window_handles_chain_edges() -> None:
    contracts = [
        cli_app.OptionContract(strikePrice=Decimal(str(strike))) for strike in range(250, 370, 5)
    ]
    visible_option_contracts = _cli_private("_visible_option_contracts")

    low_visible = visible_option_contracts(contracts, Decimal("255"))
    high_visible = visible_option_contracts(contracts, Decimal("360"))

    assert [contract.strike_price for contract in low_visible] == [
        Decimal("250"),
        Decimal("255"),
        Decimal("260"),
        Decimal("265"),
        Decimal("270"),
        Decimal("275"),
        Decimal("280"),
    ]
    assert [contract.strike_price for contract in high_visible] == [
        Decimal("335"),
        Decimal("340"),
        Decimal("345"),
        Decimal("350"),
        Decimal("355"),
        Decimal("360"),
        Decimal("365"),
    ]


def test_orders_demo_no_accounts_exits_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["orders", "demo", "--profile", "empty-accounts"])

    assert result.exit_code == 1
    assert "No accounts found." in result.output


def test_orders_demo_equity_preview_only(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        ["orders", "demo"],
        input="1\n1\ndemoorder\nAAPL\n1\n\n100\nn\n",
    )

    assert result.exit_code == 0
    assert "Selected accountIdKey: fake-account-key" in result.output
    assert "Generated preview request" in result.output
    assert "Preview IDs: 123" in result.output
    assert "Order placement skipped." in result.output
    client = FakeClient.instances[0]
    assert client.order_preview_account_id_key == "fake-account-key"
    assert client.order_preview_request is not None
    assert client.order_preview_request.client_order_id == "demoorder"
    assert client.order_preview_request.orders[0].limit_price == Decimal("100")
    assert client.order_place_request is None


def test_orders_demo_preview_prints_wire_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        ["orders", "demo"],
        input="1\n1\ndemoorder\nAAPL\n1\n\n100\nn\n",
    )

    assert result.exit_code == 0
    assert '"PreviewOrderRequest"' in result.output
    assert "broker_metadata" not in result.output


def test_orders_demo_reprompts_for_invalid_client_order_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        ["orders", "demo"],
        input="1\n1\ndemo-order\ndemoorder\nAAPL\n1\n\n100\nn\n",
    )

    assert result.exit_code == 0
    assert "Client order ID must be 1-20 alphanumeric characters." in result.output
    assert FakeClient.instances[0].order_preview_request is not None
    assert FakeClient.instances[0].order_preview_request.client_order_id == "demoorder"


def test_orders_demo_full_order_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        ["orders", "demo"],
        input="1\n1\ndemoorder\nAAPL\n1\n\n100\ny\ny\n101\ny\ny\ny\n",
    )

    assert result.exit_code == 0
    assert "Place response:" in result.output
    assert "Change preview response:" in result.output
    assert "Change place response:" in result.output
    assert "Cancel response:" in result.output
    client = FakeClient.instances[0]
    assert client.order_place_account_id_key == "fake-account-key"
    assert client.order_place_request is not None
    assert client.order_place_request.preview_ids[0].preview_id == 123
    assert client.order_preview_change_order_id == 456
    assert client.order_preview_change_request is not None
    assert client.order_preview_change_request.orders[0].limit_price == Decimal("101")
    assert client.order_preview_change_request.client_order_id != "demoorder"
    assert client.order_preview_change_request.client_order_id.startswith("epdemo")
    assert client.order_place_change_order_id == 456
    assert client.order_place_change_request is not None
    assert (
        client.order_place_change_request.client_order_id
        == client.order_preview_change_request.client_order_id
    )
    assert "Current order ID: 789" in result.output
    assert client.order_cancel_order_id == 789


@pytest.mark.parametrize(
    ("scenario_input", "expected_order_type"),
    [
        ("2\ndemooption\nAAPL\n\n1\n\n\n\nn\n", "OPTN"),
        ("3\ndemovertical\nAAPL\n\n\n4\n5\n\n\nn\n", "SPREADS"),
        ("4\ndemothree\nAAPL\n\n\n3\n5\n1\n\n\nn\n", "SPREADS"),
        ("5\ndemocondor\nAAPL\n\n\n2\n1\n6\n7\n\n\nn\n", "SPREADS"),
        ("6\ndemobuywrite\nAAPL\n\n\n\n6\n\nn\n", "BUY_WRITES"),
    ],
)
def test_orders_demo_scenarios_preview_only(
    monkeypatch: pytest.MonkeyPatch, scenario_input: str, expected_order_type: str
) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["orders", "demo"], input="1\n" + scenario_input)

    assert result.exit_code == 0
    assert "Generated preview request" in result.output
    client = FakeClient.instances[0]
    assert client.order_preview_request is not None
    assert client.order_preview_request.order_type == expected_order_type
    assert client.order_place_request is None


@pytest.mark.parametrize(
    ("short_bid", "long_ask", "price_input", "expected_price_type", "expected_price"),
    [
        ("3", "1", "\n\n", "NET_CREDIT", "4"),
        ("1", "3", "\n\n", "NET_DEBIT", "4"),
        ("3", None, "\n4\n", "NET_CREDIT", "4"),
        ("3", "1", "NET_DEBIT\n7.50\n", "NET_DEBIT", "7.50"),
    ],
)
def test_orders_demo_iron_condor_net_price(
    monkeypatch: pytest.MonkeyPatch,
    short_bid: str,
    long_ask: str | None,
    price_input: str,
    expected_price_type: str,
    expected_price: str,
) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)
    chain = OptionChainResponse.model_validate(
        {
            "nearPrice": "200",
            "OptionPair": [
                {"Put": {"strikePrice": "180", "ask": long_ask}},
                {"Put": {"strikePrice": "190", "bid": short_bid}},
                {"Call": {"strikePrice": "210", "bid": short_bid}},
                {"Call": {"strikePrice": "220", "ask": long_ask}},
            ],
        }
    )

    async def get_option_chain(
        self: FakeMarket, symbol: str, request: OptionChainRequest | None = None
    ) -> OptionChainResponse:
        return chain

    monkeypatch.setattr(FakeMarket, "get_option_chain", get_option_chain)
    result = runner.invoke(
        app,
        ["orders", "demo"],
        input="1\n5\ndemocondor\nAAPL\n\n\n2\n1\n1\n2\n" + price_input + "n\n",
    )

    assert result.exit_code == 0
    request = FakeClient.instances[0].order_preview_request
    assert request is not None
    detail = request.orders[0]
    assert detail.price_type == expected_price_type
    assert detail.limit_price == Decimal(expected_price)
    assert FakeClient.instances[0].order_place_request is None


def test_orders_demo_buy_write_reprompts_for_uncovered_ratio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        ["orders", "demo"],
        input="1\n6\ndemobuywrite\nAAPL\n\n100\n2\n200\n2\n6\n\nn\n",
    )

    assert result.exit_code == 0
    assert "Buy-write quantity must be 100 shares for each short call contract." in result.output
    client = FakeClient.instances[0]
    assert client.order_preview_request is not None
    detail = client.order_preview_request.orders[0]
    assert detail.limit_price == Decimal("1173.90")
    assert detail.instruments[0].quantity == Decimal("200")
    assert detail.instruments[1].quantity == Decimal("2")


def test_orders_demo_reprompts_for_invalid_choices_and_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        ["orders", "demo"],
        input=("x\n99\n1\nnope\n9\n1\n\n\nAAPL\nbad-action\n1\nabc\n0\n1\nabc\n0\n100\nn\n"),
    )

    assert result.exit_code == 0
    assert "Enter a numbered choice." in result.output
    assert "Enter a numbered choice from the menu." in result.output
    assert "Quantity must be a decimal number." in result.output
    assert "Quantity must be greater than zero." in result.output
    assert "Limit price must be a decimal number." in result.output
    assert "Limit price must be greater than zero." in result.output
    assert FakeClient.instances[0].order_preview_request is not None


def test_orders_demo_uses_third_friday_fallback_when_no_expirations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        ["orders", "demo", "--profile", "empty-expirations"],
        input="1\n2\ndemooption\nAAPL\n\n\n\n1\n\n\n3.25\nn\n",
    )

    assert result.exit_code == 0
    assert "third-Friday fallback" in result.output
    request = FakeClient.instances[0].order_preview_request
    assert request is not None
    product = request.orders[0].instruments[0].product
    assert (product.expiry_year, product.expiry_month, product.expiry_day) == (2026, 10, 16)


def test_orders_demo_missing_chain_quote_falls_back_to_manual_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        ["orders", "demo", "--profile", "empty-chain"],
        input="1\n2\ndemooption\nAAPL\n\n1\n200\n\n3.25\nn\n",
    )

    assert result.exit_code == 0
    assert "No call quote found for strike 200" in result.output
    assert FakeClient.instances[0].order_preview_request is not None


def test_orders_demo_reprompts_for_unavailable_chain_strike(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        ["orders", "demo"],
        input="1\n2\ndemooption\nAAPL\n\n1\n125\n5\n\n\nn\n",
    )

    assert result.exit_code == 0
    assert "Available call strikes:" in result.output
    assert "Enter a numbered strike from the list." in result.output
    client = FakeClient.instances[0]
    assert client.order_preview_request is not None
    assert client.order_preview_request.orders[0].instruments[0].product.strike_price == Decimal(
        "200"
    )


def test_orders_demo_uses_nearest_expiration_when_no_monthly_expiration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        ["orders", "demo", "--profile", "weekly-expirations"],
        input="1\n2\ndemooption\nAAPL\n\n1\n\n\n3.25\nn\n",
    )

    assert result.exit_code == 0
    assert "2026-10-09 WEEKLY [default]" in result.output
    client = FakeClient.instances[0]
    assert client.order_preview_request is not None
    assert client.order_preview_request.orders[0].instruments[0].product.expiry_day == 9


def test_orders_demo_reprompts_for_invalid_net_price_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        ["orders", "demo"],
        input="1\n3\ndemovertical\nAAPL\n\n\n4\n5\nBAD\nNET_DEBIT\n1.00\nn\n",
    )

    assert result.exit_code == 0
    assert "Price type must be NET_DEBIT or NET_CREDIT." in result.output
    assert FakeClient.instances[0].order_preview_request is not None


def test_orders_demo_no_preview_ids_skips_placement(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        ["orders", "demo", "--profile", "no-preview-ids"],
        input="1\n1\ndemoorder\nAAPL\n1\n\n100\n",
    )

    assert result.exit_code == 0
    assert "No preview IDs were returned; skipping placement." in result.output
    assert FakeClient.instances[0].order_place_request is None


def test_orders_demo_production_warning_before_place(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setenv("ETRADE_ENVIRONMENT", "production")
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(
        app,
        ["orders", "demo"],
        input="1\n1\ndemoorder\nAAPL\n1\n\n100\nn\n",
    )

    assert result.exit_code == 0
    assert "Production environment: this action affects a real brokerage account." in result.output
    assert FakeClient.instances[0].order_place_request is None


def test_orders_invalid_request_file_exits_cleanly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)
    path = tmp_path / "bad.json"
    path.write_text("not-json")

    result = runner.invoke(app, ["orders", "preview", "fake-account-key", str(path)])

    assert result.exit_code != 0
    assert FakeClient.instances == []
