from decimal import Decimal

import pytest
from pydantic import SecretStr
from typer.testing import CliRunner

from etrade_python import (
    Account,
    AccountBalanceRequest,
    AccountBalanceResponse,
    AccountListResponse,
    ETradeValidationError,
)
from etrade_python.auth import AuthorizationUrl, RequestToken, TokenStatus
from etrade_python.cli.app import app

runner = CliRunner()


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


class FakeClient:
    instances: list["FakeClient"] = []

    def __init__(self, settings: object, *, profile: str) -> None:
        self.oauth = FakeOAuth()
        self.session = FakeSession()
        self.accounts = FakeAccounts(self)
        self.profile = profile
        self.balance_account_id_key: str | None = None
        self.balance_request: AccountBalanceRequest | None = None
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
