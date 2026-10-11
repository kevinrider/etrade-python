"""Portfolio API service."""

from collections.abc import AsyncIterator
from typing import Any, cast

from pydantic import ValidationError

from etrade_python.exceptions import ETradeResponseError, ETradeValidationError
from etrade_python.portfolio.models import PortfolioRequest, PortfolioResponse, Position
from etrade_python.transport.http import ApiTransport
from etrade_python.transport.response import (
    JsonValue,
    raise_response_validation_error,
    validate_response_shape,
)
from etrade_python.transport.retry import RetrySafety


class PortfolioService:
    """Access E*TRADE portfolio endpoints."""

    def __init__(self, transport: ApiTransport) -> None:
        self._transport = transport

    async def get_positions(
        self, account_id_key: str, request: PortfolioRequest | None = None
    ) -> PortfolioResponse:
        if not account_id_key.strip():
            raise ETradeValidationError("account_id_key is required")

        portfolio_request = request or PortfolioRequest()
        response = await self._transport.request(
            "GET",
            f"/v1/accounts/{account_id_key}/portfolio.json",
            params=portfolio_request.query_params(),
            safety=RetrySafety.SAFE_READ,
            operation="portfolio.positions",
        )
        if response.status_code == 204 and response.data is None:
            return PortfolioResponse(accountPortfolio=[])
        data = _require_mapping(response.data)
        portfolio_data = _unwrap(data, "PortfolioResponse")
        try:
            return validate_response_shape(
                PortfolioResponse.model_validate(portfolio_data),
                "portfolio",
                collection_field="account_portfolios",
            )
        except ValidationError as error:
            raise_response_validation_error("Invalid portfolio response", error)

    async def iter_positions(
        self, account_id_key: str, request: PortfolioRequest | None = None
    ) -> AsyncIterator[Position]:
        """Iterate positions using the broker's nextPageNo continuation field."""
        base_request = request or PortfolioRequest()
        current_request = base_request
        seen_pages = {base_request.page_number or 1}
        while True:
            page = await self.get_positions(account_id_key, current_request)
            next_page = _next_page_number(page)
            if next_page in seen_pages:
                raise ETradeResponseError("Portfolio pagination did not advance")
            for account_portfolio in page.account_portfolios:
                for position in account_portfolio.positions:
                    yield position
            if next_page is None:
                return
            seen_pages.add(next_page)
            current_request = base_request.model_copy(update={"page_number": next_page})


def _require_mapping(data: JsonValue) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ETradeResponseError("Invalid portfolio response")
    return cast(dict[str, Any], data)


def _unwrap(data: dict[str, Any], envelope: str) -> dict[str, Any]:
    value = data.get(envelope, data)
    if not isinstance(value, dict):
        raise ETradeResponseError("Invalid portfolio response")
    return cast(dict[str, Any], value)


def _next_page_number(response: PortfolioResponse) -> int | None:
    for account_portfolio in response.account_portfolios:
        page_number = account_portfolio.next_page_no
        if page_number:
            try:
                next_page = int(page_number)
            except ValueError:
                raise ETradeResponseError("Invalid portfolio pagination page number") from None
            if next_page < 1:
                raise ETradeResponseError("Invalid portfolio pagination page number")
            return next_page
        if account_portfolio.next:
            raise ETradeResponseError("Portfolio pagination is missing the next page number")
    return None
