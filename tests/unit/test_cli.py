import pytest
from pydantic import SecretStr
from typer.testing import CliRunner

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


class FakeClient:
    def __init__(self, settings: object, *, profile: str) -> None:
        self.oauth = FakeOAuth()
        self.session = FakeSession()
        self.profile = profile

    async def __aenter__(self) -> "FakeClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


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
