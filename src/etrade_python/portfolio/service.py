"""Portfolio API service."""

from collections.abc import AsyncIterator
from typing import Any, cast

from pydantic import ValidationError

from etrade_python.exceptions import ETradeResponseError, ETradeValidationError
from etrade_python.portfolio.models import PortfolioRequest, PortfolioResponse, Position
from etrade_python.transport.http import ApiTransport
from etrade_python.transport.response import JsonValue
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
        if response.data is None:
            return PortfolioResponse(accountPortfolio=[])
        data = _require_mapping(response.data)
        portfolio_data = _unwrap(data, "PortfolioResponse")
        if not _looks_like_portfolio_response(portfolio_data):
            raise ETradeResponseError("Invalid portfolio response")
        try:
            return PortfolioResponse.model_validate(portfolio_data)
        except ValidationError:
            raise ETradeResponseError("Invalid portfolio response") from None

    async def iter_positions(
        self, account_id_key: str, request: PortfolioRequest | None = None
    ) -> AsyncIterator[Position]:
        base_request = request or PortfolioRequest()
        current_request = base_request
        while True:
            page = await self.get_positions(account_id_key, current_request)
            for account_portfolio in page.account_portfolios:
                for position in account_portfolio.positions:
                    yield position
            marker = _next_marker(page)
            if not marker:
                return
            current_request = base_request.model_copy(update={"page_number": int(marker)})


def _require_mapping(data: JsonValue) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ETradeResponseError("Invalid portfolio response")
    return cast(dict[str, Any], data)


def _unwrap(data: dict[str, Any], envelope: str) -> dict[str, Any]:
    value = data.get(envelope, data)
    if not isinstance(value, dict):
        raise ETradeResponseError("Invalid portfolio response")
    return cast(dict[str, Any], value)


def _next_marker(response: PortfolioResponse) -> str | None:
    for account_portfolio in response.account_portfolios:
        marker = account_portfolio.next or account_portfolio.next_page_no
        if marker:
            return marker
    return None


def _looks_like_portfolio_response(data: dict[str, Any]) -> bool:
    return any(key in data for key in ("AccountPortfolio", "accountPortfolio", "Totals", "totals"))
