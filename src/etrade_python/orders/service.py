"""Orders API service."""

from collections.abc import AsyncIterator
from typing import Any, cast

from pydantic import ValidationError

from etrade_python.exceptions import ETradeResponseError, ETradeValidationError
from etrade_python.orders.models import (
    CancelOrderRequest,
    CancelOrderResponse,
    Order,
    OrdersRequest,
    OrdersResponse,
    PlaceOrderRequest,
    PlaceOrderResponse,
    PreviewOrderRequest,
    PreviewOrderResponse,
)
from etrade_python.transport.http import ApiTransport
from etrade_python.transport.response import (
    JsonValue,
    raise_response_validation_error,
    validate_response_shape,
)
from etrade_python.transport.retry import RetrySafety


class OrdersService:
    """Access E*TRADE order endpoints."""

    def __init__(self, transport: ApiTransport) -> None:
        self._transport = transport

    async def list(
        self, account_id_key: str, request: OrdersRequest | None = None
    ) -> OrdersResponse:
        account_id_key = _normalize_required(account_id_key, "account_id_key")
        orders_request = request or OrdersRequest()
        response = await self._transport.request(
            "GET",
            f"/v1/accounts/{account_id_key}/orders.json",
            params=orders_request.query_params(),
            safety=RetrySafety.SAFE_READ,
            operation="orders.list",
        )
        if response.status_code == 204 and response.data is None:
            return OrdersResponse(order=[])
        data = _require_mapping(response.data, "orders")
        orders_data = _unwrap(data, "OrdersResponse", "orders")
        try:
            return validate_response_shape(
                OrdersResponse.model_validate(orders_data), "orders", collection_field="orders"
            )
        except ValidationError as error:
            raise_response_validation_error("Invalid orders response", error)

    async def list_all(
        self, account_id_key: str, request: OrdersRequest | None = None
    ) -> AsyncIterator[Order]:
        """Iterate orders until the broker returns an empty continuation marker."""
        base_request = request or OrdersRequest()
        current_request = base_request
        seen_markers: set[str] = {base_request.marker} if base_request.marker else set()
        while True:
            page = await self.list(account_id_key, current_request)
            marker = page.marker
            if marker and marker in seen_markers:
                raise ETradeResponseError("Order pagination did not advance")
            for order in page.orders:
                yield order
            if not marker:
                return
            seen_markers.add(marker)
            current_request = base_request.model_copy(update={"marker": marker})

    async def preview(
        self, account_id_key: str, request: PreviewOrderRequest
    ) -> PreviewOrderResponse:
        account_id_key = _normalize_required(account_id_key, "account_id_key")
        response = await self._transport.request(
            "POST",
            f"/v1/accounts/{account_id_key}/orders/preview.json",
            body=request.request_body(),
            safety=RetrySafety.NEVER,
            operation="orders.preview",
        )
        data = _require_mapping(response.data, "preview order")
        preview_data = _unwrap(data, "PreviewOrderResponse", "preview order")
        try:
            parsed = validate_response_shape(
                PreviewOrderResponse.model_validate(preview_data), "preview order"
            )
            _require_confirmation(parsed, preview_data, "preview order")
            return parsed
        except ValidationError as error:
            raise_response_validation_error("Invalid preview order response", error)

    async def place(self, account_id_key: str, request: PlaceOrderRequest) -> PlaceOrderResponse:
        account_id_key = _normalize_required(account_id_key, "account_id_key")
        response = await self._transport.request(
            "POST",
            f"/v1/accounts/{account_id_key}/orders/place.json",
            body=request.request_body(),
            safety=RetrySafety.NEVER,
            operation="orders.place",
        )
        data = _require_mapping(response.data, "place order")
        place_data = _unwrap(data, "PlaceOrderResponse", "place order")
        try:
            parsed = validate_response_shape(
                PlaceOrderResponse.model_validate(place_data), "place order"
            )
            _require_confirmation(parsed, place_data, "place order")
            return parsed
        except ValidationError as error:
            raise_response_validation_error("Invalid place order response", error)

    async def preview_change(
        self, account_id_key: str, order_id: int, request: PreviewOrderRequest
    ) -> PreviewOrderResponse:
        account_id_key = _normalize_required(account_id_key, "account_id_key")
        order_id = _normalize_order_id(order_id)
        response = await self._transport.request(
            "PUT",
            f"/v1/accounts/{account_id_key}/orders/{order_id}/change/preview.json",
            body=request.request_body(),
            safety=RetrySafety.NEVER,
            operation="orders.preview_change",
        )
        data = _require_mapping(response.data, "preview changed order")
        preview_data = _unwrap(data, "PreviewOrderResponse", "preview changed order")
        try:
            parsed = validate_response_shape(
                PreviewOrderResponse.model_validate(preview_data), "preview changed order"
            )
            _require_confirmation(parsed, preview_data, "preview changed order")
            return parsed
        except ValidationError as error:
            raise_response_validation_error("Invalid preview changed order response", error)

    async def place_change(
        self, account_id_key: str, order_id: int, request: PlaceOrderRequest
    ) -> PlaceOrderResponse:
        account_id_key = _normalize_required(account_id_key, "account_id_key")
        order_id = _normalize_order_id(order_id)
        response = await self._transport.request(
            "PUT",
            f"/v1/accounts/{account_id_key}/orders/{order_id}/change/place.json",
            body=request.request_body(),
            safety=RetrySafety.NEVER,
            operation="orders.place_change",
        )
        data = _require_mapping(response.data, "place changed order")
        place_data = _unwrap(data, "PlaceOrderResponse", "place changed order")
        try:
            parsed = validate_response_shape(
                PlaceOrderResponse.model_validate(place_data), "place changed order"
            )
            _require_confirmation(parsed, place_data, "place changed order")
            return parsed
        except ValidationError as error:
            raise_response_validation_error("Invalid place changed order response", error)

    async def cancel(self, account_id_key: str, order_id: int) -> CancelOrderResponse:
        account_id_key = _normalize_required(account_id_key, "account_id_key")
        order_id = _normalize_order_id(order_id)
        request = CancelOrderRequest(orderId=order_id)
        response = await self._transport.request(
            "PUT",
            f"/v1/accounts/{account_id_key}/orders/cancel.json",
            body=request.request_body(),
            safety=RetrySafety.NEVER,
            operation="orders.cancel",
        )
        data = _require_mapping(response.data, "cancel order")
        cancel_data = _unwrap(data, "CancelOrderResponse", "cancel order")
        try:
            parsed = validate_response_shape(
                CancelOrderResponse.model_validate(cancel_data), "cancel order"
            )
            _require_confirmation(parsed, cancel_data, "cancel order")
            return parsed
        except ValidationError as error:
            raise_response_validation_error("Invalid cancel order response", error)


def _normalize_required(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ETradeValidationError(f"{label} is required")
    return normalized


def _require_confirmation(
    response: PreviewOrderResponse | PlaceOrderResponse | CancelOrderResponse,
    data: dict[str, Any],
    response_name: str,
) -> None:
    if isinstance(response, PreviewOrderResponse):
        ids = [preview.preview_id for preview in response.preview_ids]
        raw_ids = data.get("PreviewIds", data.get("previewIds", data.get("preview_ids")))
        has_boolean = _contains_boolean_id(raw_ids, "previewId", "PreviewId")
    elif isinstance(response, PlaceOrderResponse):
        ids = [order.order_id for order in response.order_ids]
        if response.order_id is not None:
            ids.append(response.order_id)
        raw_ids = data.get("OrderIds", data.get("orderIds", data.get("order_ids")))
        has_boolean = _contains_boolean_id(raw_ids, "orderId", "OrderId") or isinstance(
            data.get("orderId", data.get("order_id")), bool
        )
    else:
        ids = [] if response.order_id is None else [response.order_id]
        has_boolean = isinstance(data.get("orderId", data.get("order_id")), bool)
    if (
        has_boolean
        or not ids
        or any(type(identifier) is not int or identifier <= 0 for identifier in ids)
    ):
        raise ETradeResponseError(
            f"Invalid {response_name} response: missing or invalid confirmation ID"
        )


def _contains_boolean_id(value: object, field: str, wrapper: str) -> bool:
    """Prevent permissive response integer coercion from treating True as ID 1."""
    if isinstance(value, bool):
        return True
    if isinstance(value, list):
        return any(_contains_boolean_id(item, field, wrapper) for item in cast(list[object], value))
    if isinstance(value, dict):
        data = cast(dict[str, object], value)
        if wrapper in data:
            return _contains_boolean_id(data[wrapper], field, wrapper)
        return _contains_boolean_id(
            data.get(field, data.get("preview_id" if field == "previewId" else "order_id")),
            field,
            wrapper,
        )
    return False


def _normalize_order_id(order_id: int) -> int:
    if type(order_id) is not int or order_id < 1:
        raise ETradeValidationError("order_id must be a positive integer")
    return order_id


def _require_mapping(data: JsonValue, response_name: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ETradeResponseError(f"Invalid {response_name} response")
    return cast(dict[str, Any], data)


def _unwrap(data: dict[str, Any], envelope: str, response_name: str) -> dict[str, Any]:
    value = data.get(envelope, data)
    if not isinstance(value, dict):
        raise ETradeResponseError(f"Invalid {response_name} response")
    return cast(dict[str, Any], value)
