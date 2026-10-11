"""Alerts API service."""

from collections.abc import Sequence
from typing import Any, cast

from pydantic import ValidationError

from etrade_python.alerts.models import (
    AlertDetailsRequest,
    AlertDetailsResponse,
    AlertsRequest,
    AlertsResponse,
    DeleteAlertsResponse,
)
from etrade_python.exceptions import ETradeNotFoundError, ETradeResponseError, ETradeValidationError
from etrade_python.transport.http import ApiTransport
from etrade_python.transport.response import (
    JsonValue,
    raise_response_validation_error,
    validate_response_shape,
)
from etrade_python.transport.retry import RetrySafety


class AlertsService:
    """Access E*TRADE alert endpoints."""

    def __init__(self, transport: ApiTransport) -> None:
        self._transport = transport

    async def list(self, request: AlertsRequest | None = None) -> AlertsResponse:
        alerts_request = request or AlertsRequest()
        try:
            response = await self._transport.request(
                "GET",
                "/v1/user/alerts.json",
                params=alerts_request.query_params(),
                safety=RetrySafety.SAFE_READ,
                operation="alerts.list",
            )
        except ETradeNotFoundError as error:
            if _is_no_alerts_error(error):
                return AlertsResponse(totalAlerts=0, alerts=[])
            raise
        if response.status_code == 204 and response.data is None:
            return AlertsResponse(totalAlerts=0, alerts=[])
        data = _require_mapping(response.data, "alerts")
        alerts_data = _unwrap(data, "AlertsResponse", "alerts")
        try:
            return validate_response_shape(
                AlertsResponse.model_validate(alerts_data), "alerts", collection_field="alerts"
            )
        except ValidationError as error:
            raise_response_validation_error("Invalid alerts response", error)

    async def get(
        self, alert_id: int, request: AlertDetailsRequest | None = None
    ) -> AlertDetailsResponse:
        normalized_id = _normalize_alert_id(alert_id)
        details_request = request or AlertDetailsRequest()
        response = await self._transport.request(
            "GET",
            f"/v1/user/alerts/{normalized_id}.json",
            params=details_request.query_params(),
            safety=RetrySafety.SAFE_READ,
            operation="alerts.get",
        )
        data = _require_mapping(response.data, "alert details")
        details_data = _unwrap(data, "AlertDetailsResponse", "alert details")
        try:
            return validate_response_shape(
                AlertDetailsResponse.model_validate(details_data), "alert details"
            )
        except ValidationError as error:
            raise_response_validation_error("Invalid alert details response", error)

    async def delete(self, alert_ids: Sequence[int] | int) -> DeleteAlertsResponse:
        ids = _normalize_alert_ids(alert_ids)
        response = await self._transport.request(
            "DELETE",
            f"/v1/user/alerts/{','.join(str(alert_id) for alert_id in ids)}.json",
            safety=RetrySafety.NEVER,
            operation="alerts.delete",
        )
        data = _require_mapping(response.data, "delete alerts")
        delete_data = _unwrap(data, "DeleteAlertsResponse", "delete alerts")
        try:
            return validate_response_shape(
                DeleteAlertsResponse.model_validate(delete_data), "delete alerts"
            )
        except ValidationError as error:
            raise_response_validation_error("Invalid delete alerts response", error)


def _normalize_alert_id(alert_id: int) -> int:
    if type(alert_id) is not int or alert_id < 1:
        raise ETradeValidationError("alert_id must be a positive integer")
    return alert_id


def _normalize_alert_ids(alert_ids: Sequence[int] | int) -> list[int]:
    if isinstance(alert_ids, bool):
        raise ETradeValidationError("alert_ids must be integers")
    if isinstance(alert_ids, int):
        return [_normalize_alert_id(alert_ids)]
    if isinstance(alert_ids, (str, bytes)) or not isinstance(cast(object, alert_ids), Sequence):
        raise ETradeValidationError("alert_ids must be integers")
    normalized = [_normalize_alert_id(alert_id) for alert_id in alert_ids]
    if not normalized:
        raise ETradeValidationError("at least one alert_id is required")
    return normalized


def _is_no_alerts_error(error: ETradeNotFoundError) -> bool:
    return error.broker_code == "53" or "no alerts" in (error.broker_message or "").lower()


def _require_mapping(data: JsonValue, response_name: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ETradeResponseError(f"Invalid {response_name} response")
    return cast(dict[str, Any], data)


def _unwrap(data: dict[str, Any], envelope: str, response_name: str) -> dict[str, Any]:
    value = data.get(envelope, data)
    if not isinstance(value, dict):
        raise ETradeResponseError(f"Invalid {response_name} response")
    return cast(dict[str, Any], value)
