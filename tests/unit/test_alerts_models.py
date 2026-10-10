from datetime import UTC, datetime

import pytest

from etrade_python import AlertDetailsRequest, AlertsRequest
from etrade_python.alerts import AlertDetailsResponse, AlertsResponse, DeleteAlertsResponse
from tests.conftest import load_json_fixture


def test_alerts_request_query_params() -> None:
    request = AlertsRequest(
        count=25, category="stock", status="unread", direction="desc", search="AAPL"
    )

    assert request.query_params() == {
        "count": 25,
        "category": "STOCK",
        "status": "UNREAD",
        "direction": "DESC",
        "search": "AAPL",
    }


def test_alerts_request_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="category"):
        AlertsRequest(category="BAD")
    with pytest.raises(ValueError, match="status"):
        AlertsRequest(status="BAD")
    with pytest.raises(ValueError, match="direction"):
        AlertsRequest(direction="BAD")
    with pytest.raises(ValueError, match="nonempty"):
        AlertsRequest(search=" ")


def test_alert_details_request_query_params() -> None:
    assert AlertDetailsRequest(htmlTags=True).query_params() == {"htmlTags": "true"}
    assert AlertDetailsRequest(htmlTags=False).query_params() == {"htmlTags": "false"}
    assert AlertDetailsRequest().query_params() == {"htmlTags": None}


@pytest.mark.parametrize("html_tags", [True, False, None])
def test_alert_details_request_accepts_python_field_name(html_tags: bool | None) -> None:
    request = AlertDetailsRequest.model_validate({"html_tags": html_tags})
    aliased_request = AlertDetailsRequest(htmlTags=html_tags)

    assert request.html_tags is html_tags
    assert request.query_params() == aliased_request.query_params()


def test_alerts_response_parses_fixture() -> None:
    response = AlertsResponse.model_validate(
        load_json_fixture("responses/alerts_response.json")["AlertsResponse"]
    )

    assert response.total_alerts == 148
    assert len(response.alerts) == 2
    assert response.alerts[0].id == 6774
    assert response.alerts[0].create_time == datetime(2018, 6, 19, 16, 40, 2, tzinfo=UTC)
    assert response.alerts[1].subject == "AAPL down by at least 2.00%"


def test_alert_details_response_parses_fixture() -> None:
    response = AlertDetailsResponse.model_validate(
        load_json_fixture("responses/alert_details_response.json")["AlertDetailsResponse"]
    )

    assert response.id == 6773
    assert response.symbol == "AAPL"
    assert response.read_time is None
    assert response.delete_time is None
    assert response.create_time == datetime(2018, 6, 19, 14, 0, 25, tzinfo=UTC)
    assert "APPLE" in (response.msg_text or "")


def test_delete_alerts_response_parses_fixtures() -> None:
    response = DeleteAlertsResponse.model_validate(
        load_json_fixture("responses/delete_alerts_response.json")["DeleteAlertsResponse"]
    )
    failed = DeleteAlertsResponse.model_validate(
        load_json_fixture("responses/delete_alerts_failed_response.json")["DeleteAlertsResponse"]
    )

    assert response.result == "SUCCESS"
    assert failed.failed_alerts is not None
    assert failed.failed_alerts.alert_ids == [6772, 6774]


def test_alert_response_normalizes_single_and_empty_values() -> None:
    response = AlertsResponse.model_validate({"Alert": {"id": 1, "createTime": "0"}})
    empty = AlertsResponse.model_validate({"alerts": None})
    failed = DeleteAlertsResponse.model_validate({"FailedAlerts": {"alertId": 1}})

    assert response.alerts[0].create_time is None
    assert empty.alerts == []
    assert failed.failed_alerts is not None
    assert failed.failed_alerts.alert_ids == [1]
