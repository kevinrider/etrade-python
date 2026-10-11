"""Accounts API service."""

from typing import Any, cast

from pydantic import ValidationError

from etrade_python.accounts.models import (
    Account,
    AccountBalanceRequest,
    AccountBalanceResponse,
    AccountListResponse,
)
from etrade_python.exceptions import ETradeResponseError, ETradeValidationError
from etrade_python.transport.http import ApiTransport
from etrade_python.transport.response import (
    JsonValue,
    raise_response_validation_error,
    validate_response_shape,
)
from etrade_python.transport.retry import RetrySafety


class AccountsService:
    """Access E*TRADE account list and balance endpoints."""

    def __init__(self, transport: ApiTransport) -> None:
        self._transport = transport

    async def list(self) -> AccountListResponse:
        response = await self._transport.request(
            "GET",
            "/v1/accounts/list.json",
            safety=RetrySafety.SAFE_READ,
            operation="accounts.list",
        )
        if response.status_code == 204 and response.data is None:
            return AccountListResponse(accounts=[])

        data = _require_mapping(response.data)
        accounts_data = _unwrap(data, "AccountListResponse")
        accounts_container = _optional_mapping(accounts_data, "accounts", "Accounts")
        if accounts_container is None:
            raise ETradeResponseError("Invalid account list response")

        raw_accounts_value = _optional_value(accounts_container, "account", "Account")
        if raw_accounts_value is None:
            if not any(key in accounts_container for key in ("account", "Account")):
                raise ETradeResponseError("Invalid account list response: missing collection")
            return AccountListResponse(accounts=[])
        if isinstance(raw_accounts_value, dict):
            raw_accounts: list[Any] = [raw_accounts_value]
        elif isinstance(raw_accounts_value, list):
            raw_accounts = cast(list[Any], raw_accounts_value)
        else:
            raise ETradeResponseError("Invalid account list response")

        accounts: list[Account] = []
        for index, account in enumerate(raw_accounts):
            try:
                accounts.append(
                    validate_response_shape(Account.model_validate(account), "account list")
                )
            except ValidationError as error:
                raise_response_validation_error(
                    "Invalid account list response", error, prefix=f"accounts.{index}"
                )
        return AccountListResponse(accounts=accounts)

    async def get_balance(
        self, account_id_key: str, request: AccountBalanceRequest | None = None
    ) -> AccountBalanceResponse:
        if not account_id_key.strip():
            raise ETradeValidationError("account_id_key is required")

        balance_request = request or AccountBalanceRequest()
        response = await self._transport.request(
            "GET",
            f"/v1/accounts/{account_id_key}/balance.json",
            params=balance_request.query_params(),
            safety=RetrySafety.SAFE_READ,
            operation="accounts.balance",
        )
        data = _require_mapping(response.data)
        balance_data = _unwrap(data, "BalanceResponse")
        try:
            return validate_response_shape(
                AccountBalanceResponse.model_validate(_normalize_balance(balance_data)),
                "account balance",
            )
        except ValidationError as error:
            raise_response_validation_error("Invalid account balance response", error)


def _require_mapping(data: JsonValue) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ETradeResponseError("Invalid account response")
    return cast(dict[str, Any], data)


def _unwrap(data: dict[str, Any], envelope: str) -> dict[str, Any]:
    value = data.get(envelope, data)
    if not isinstance(value, dict):
        raise ETradeResponseError("Invalid account response")
    return cast(dict[str, Any], value)


def _optional_mapping(data: dict[str, Any], *keys: str) -> dict[str, Any] | None:
    value = _optional_value(data, *keys)
    if value is None:
        return None
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return None


def _optional_value(data: dict[str, Any], *keys: str) -> Any | None:
    for key in keys:
        if key in data:
            return data[key]
    return None


def _normalize_balance(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)
    aliases = {
        "Cash": "cash",
        "Computed": "computedBalance",
        "ComputedBalance": "computedBalance",
        "Margin": "margin",
        "Lending": "lending",
    }
    for source, target in aliases.items():
        if source in normalized and target not in normalized:
            normalized[target] = normalized[source]
            del normalized[source]
    return normalized
