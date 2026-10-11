"""Transactions API service."""

from collections.abc import AsyncIterator
from typing import Any, cast

from pydantic import ValidationError

from etrade_python.exceptions import ETradeResponseError, ETradeValidationError
from etrade_python.transactions.models import (
    Transaction,
    TransactionDetailsRequest,
    TransactionDetailsResponse,
    TransactionsRequest,
    TransactionsResponse,
)
from etrade_python.transport.http import ApiTransport
from etrade_python.transport.response import (
    JsonValue,
    raise_response_validation_error,
    validate_response_shape,
)
from etrade_python.transport.retry import RetrySafety


class TransactionsService:
    """Access E*TRADE transaction endpoints."""

    def __init__(self, transport: ApiTransport) -> None:
        self._transport = transport

    async def list(
        self, account_id_key: str, request: TransactionsRequest | None = None
    ) -> TransactionsResponse:
        if not account_id_key.strip():
            raise ETradeValidationError("account_id_key is required")

        transactions_request = request or TransactionsRequest()
        response = await self._transport.request(
            "GET",
            f"/v1/accounts/{account_id_key}/transactions.json",
            params=transactions_request.query_params(),
            safety=RetrySafety.SAFE_READ,
            operation="transactions.list",
        )
        if response.status_code == 204 and response.data is None:
            return TransactionsResponse(transaction=[])
        data = _require_mapping(response.data)
        transactions_data = _unwrap(data, "TransactionListResponse")
        try:
            return validate_response_shape(
                TransactionsResponse.model_validate(transactions_data),
                "transactions",
                collection_field="transactions",
            )
        except ValidationError as error:
            raise_response_validation_error("Invalid transactions response", error)

    async def get(
        self,
        account_id_key: str,
        transaction_id: str,
        request: TransactionDetailsRequest | None = None,
    ) -> TransactionDetailsResponse:
        if not account_id_key.strip():
            raise ETradeValidationError("account_id_key is required")
        if not transaction_id.strip():
            raise ETradeValidationError("transaction_id is required")

        details_request = request or TransactionDetailsRequest()
        response = await self._transport.request(
            "GET",
            f"/v1/accounts/{account_id_key}/transactions/{transaction_id}.json",
            params=details_request.query_params(),
            safety=RetrySafety.SAFE_READ,
            operation="transactions.get",
        )
        data = _require_mapping(response.data)
        transaction_data = _unwrap(data, "TransactionDetailsResponse")
        try:
            return validate_response_shape(
                TransactionDetailsResponse.model_validate(transaction_data), "transaction details"
            )
        except ValidationError as error:
            raise_response_validation_error("Invalid transaction details response", error)

    async def list_all(
        self, account_id_key: str, request: TransactionsRequest | None = None
    ) -> AsyncIterator[Transaction]:
        """Iterate pages, omitting repeated boundary transactions.

        Automatic pagination requires count >= 2 because an inclusive marker
        cannot advance a one-record page. Single-page list() permits count=1.
        """
        base_request = request or TransactionsRequest()
        count = base_request.count or 50
        if count == 1:
            raise ETradeValidationError("Automatic transaction pagination requires count >= 2")
        current_request = base_request
        previous_last_id: str | None = None
        seen_markers: set[str] = {base_request.marker} if base_request.marker else set()
        while True:
            page = await self.list(account_id_key, current_request)
            marker = page.marker
            has_next_page = bool(marker) and len(page.transactions) >= count
            if has_next_page and marker in seen_markers:
                raise ETradeResponseError("Transaction pagination did not advance")

            transactions = page.transactions
            if (
                transactions
                and previous_last_id is not None
                and transactions[0].transaction_id is not None
                and str(transactions[0].transaction_id) == previous_last_id
            ):
                transactions = transactions[1:]
            for transaction in transactions:
                yield transaction

            if not has_next_page:
                return
            last_id = page.transactions[-1].transaction_id
            previous_last_id = str(last_id) if last_id is not None else None
            if marker is not None:
                seen_markers.add(marker)
            current_request = base_request.model_copy(update={"marker": marker})


def _require_mapping(data: JsonValue) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ETradeResponseError("Invalid transaction response")
    return cast(dict[str, Any], data)


def _unwrap(data: dict[str, Any], envelope: str) -> dict[str, Any]:
    value = data.get(envelope, data)
    if not isinstance(value, dict):
        raise ETradeResponseError("Invalid transaction response")
    return cast(dict[str, Any], value)
