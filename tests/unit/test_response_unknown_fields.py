"""Unknown response data is discarded across every API domain."""

from types import ModuleType

import pytest
from pydantic import BaseModel

from etrade_python.accounts import models as accounts
from etrade_python.alerts import models as alerts
from etrade_python.market import models as market
from etrade_python.orders import models as orders
from etrade_python.portfolio import models as portfolio
from etrade_python.transactions import models as transactions
from tests.conftest import load_json_fixture


@pytest.mark.parametrize("module", [accounts, alerts, market, orders, portfolio, transactions])
def test_response_models_have_no_metadata_field(module: ModuleType) -> None:
    for model_type in vars(module).values():
        if (
            isinstance(model_type, type)
            and issubclass(model_type, BaseModel)
            and issubclass(model_type, module.BrokerModel)
        ):
            assert model_type.model_config.get("extra") == "ignore", model_type.__name__
            assert "broker_metadata" not in model_type.model_fields
            assert "broker_metadata" not in model_type.model_json_schema()["properties"]


@pytest.mark.parametrize(
    "model_type",
    [
        accounts.Account,
        alerts.Alert,
        market.Quote,
        orders.Order,
        portfolio.Position,
        transactions.Transaction,
    ],
)
def test_responses_discard_unknown_and_legacy_metadata_fields(model_type: type[BaseModel]) -> None:
    payload: dict[str, object] = {
        "futureField": "discarded",
        "broker_metadata": {"legacyField": "discarded"},
    }
    if model_type is accounts.Account:
        payload.update({"accountId": "fake-account", "accountIdKey": "fake-key"})
    model = model_type.model_validate(payload)
    assert not hasattr(model, "futureField")
    assert not hasattr(model, "broker_metadata")
    assert model.model_extra is None
    for by_alias in (False, True):
        payload = model.model_dump(by_alias=by_alias)
        assert "futureField" not in payload
        assert "broker_metadata" not in payload
        assert "legacyField" not in model.model_dump_json(by_alias=by_alias)


@pytest.mark.parametrize(
    "model_type, fixture_name, envelope",
    [
        (orders.PreviewOrderRequest, "preview_order_request_equity.json", "PreviewOrderRequest"),
        (orders.PlaceOrderRequest, "place_order_request_equity.json", "PlaceOrderRequest"),
    ],
)
def test_order_request_extras_remain_supported_and_metadata_is_filtered(
    model_type: type[orders.PreviewOrderRequest], fixture_name: str, envelope: str
) -> None:
    payload = load_json_fixture(f"responses/{fixture_name}")[envelope]
    detail = payload["Order"][0]
    instrument = detail["Instrument"][0]
    for entry in (detail, instrument):
        entry["customField"] = "retained"
        entry["broker_metadata"] = {"legacyField": "discarded"}
    request = model_type.model_validate(payload)
    body = request.request_body()[envelope]
    assert body["Order"][0]["customField"] == "retained"
    assert body["Order"][0]["Instrument"][0]["customField"] == "retained"
    assert "broker_metadata" not in body["Order"][0]
    assert "broker_metadata" not in body["Order"][0]["Instrument"][0]
