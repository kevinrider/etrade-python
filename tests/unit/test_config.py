from pathlib import Path

import pytest

from etrade_python import Environment, ETradeSettings, ETradeValidationError
from etrade_python.enums import AUTHORIZATION_URL, OAUTH_BASE_URL


def test_defaults_and_secrets(settings: ETradeSettings) -> None:
    assert settings.environment is Environment.SANDBOX
    assert settings.request_timeout_seconds == 30
    assert settings.inactivity_buffer_seconds == 300
    assert "fake-key" not in repr(settings)
    assert "fake-secret" not in settings.model_dump_json()
    assert settings.consumer_secret.get_secret_value() == "fake-secret"
    assert Environment.SANDBOX.api_base_url == "https://apisb.etrade.com"
    assert Environment.PRODUCTION.api_base_url == "https://api.etrade.com"
    assert OAUTH_BASE_URL == "https://api.etrade.com"
    assert AUTHORIZATION_URL == "https://us.etrade.com/e/t/etws/authorize"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("consumer_key", ""),
        ("consumer_secret", "  "),
        ("consumer_secret", 123),
        ("environment", "fake-invalid-secret"),
        ("request_timeout_seconds", 0),
        ("request_timeout_seconds", -1),
        ("request_timeout_seconds", float("inf")),
        ("request_timeout_seconds", float("nan")),
        ("inactivity_buffer_seconds", -1),
        ("inactivity_buffer_seconds", 7200),
        ("inactivity_buffer_seconds", 0.5),
    ],
)
def test_invalid_settings(field: str, value: object) -> None:
    values: dict[str, object] = {"consumer_key": "fake-key", "consumer_secret": "fake-secret"}
    values[field] = value
    with pytest.raises(ETradeValidationError) as exc:
        ETradeSettings(**values)
    assert "fake-" not in str(exc.value)
    assert field in str(exc.value)


def test_missing_settings() -> None:
    with pytest.raises(ETradeValidationError, match="consumer_key, consumer_secret"):
        ETradeSettings()


def test_settings_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "ETRADE_CONSUMER_KEY=fake-file-key\nETRADE_CONSUMER_SECRET=fake-file-secret\n"
        "ETRADE_ENVIRONMENT=production\nETRADE_REQUEST_TIMEOUT_SECONDS=10\n"
    )
    with pytest.raises(ETradeValidationError):
        ETradeSettings()
    file_settings = ETradeSettings(_env_file=dotenv)
    assert file_settings.environment is Environment.PRODUCTION
    monkeypatch.setenv("ETRADE_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("ETRADE_REQUEST_TIMEOUT_SECONDS", "20")
    loaded = ETradeSettings(_env_file=dotenv, request_timeout_seconds=40)
    assert loaded.environment is Environment.SANDBOX
    assert loaded.request_timeout_seconds == 40
    assert ETradeSettings(_env_file=dotenv).request_timeout_seconds == 20
