from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr
from typer.testing import CliRunner

import etrade_python.cli.app as cli_app
from etrade_python import (
    Account,
    AccountBalanceRequest,
    AccountBalanceResponse,
    AccountListResponse,
    CancelOrderResponse,
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
from etrade_python.auth import AuthorizationUrl, RequestToken, TokenStatus
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


class FakeClient:
    instances: list["FakeClient"] = []

    def __init__(self, settings: object, *, profile: str) -> None:
        self.oauth = FakeOAuth()
        self.session = FakeSession()
        self.accounts = FakeAccounts(self)
        self.portfolio = FakePortfolio(self)
        self.transactions = FakeTransactions(self)
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


def test_market_lookup_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.setattr("etrade_python.cli.app.ETradeClient", FakeClient)

    result = runner.invoke(app, ["market", "lookup", "agilent"])

    assert result.exit_code == 0
    assert "A" in result.output
    assert "Agilent Technologies Inc." in result.output
    assert FakeClient.instances[0].market_lookup_search == "agilent"


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
    assert buy_write_estimate(
        quote, Decimal("100"), chain.option_pairs[0].call, Decimal("1")
    ) == Decimal("19680.00")


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
    assert FakeClient.instances[0].order_preview_request is not None


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
