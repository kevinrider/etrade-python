"""Market API service."""

from collections.abc import Sequence
from typing import Any, cast
from urllib.parse import quote

from pydantic import ValidationError

from etrade_python.exceptions import ETradeResponseError, ETradeValidationError
from etrade_python.market.models import (
    OptionChainRequest,
    OptionChainResponse,
    OptionExpirationsRequest,
    OptionExpirationsResponse,
    ProductLookupRequest,
    ProductLookupResponse,
    Quote,
    QuotesRequest,
    QuotesResponse,
)
from etrade_python.transport.http import ApiTransport
from etrade_python.transport.response import (
    JsonValue,
    raise_response_validation_error,
    validate_response_shape,
)
from etrade_python.transport.retry import RetrySafety


class MarketService:
    """Access E*TRADE market data endpoints."""

    def __init__(self, transport: ApiTransport) -> None:
        self._transport = transport

    async def get_quote(self, symbol: str, request: QuotesRequest | None = None) -> Quote:
        response = await self.get_quotes([symbol], request)
        if not response.quotes:
            raise ETradeResponseError("Invalid quote response: no quotes returned")
        requested = symbol.upper()
        for quote_data in response.quotes:
            if quote_data.product is not None and quote_data.product.symbol == requested:
                return quote_data
        return response.quotes[0]

    async def get_quotes(
        self, symbols: Sequence[str], request: QuotesRequest | None = None
    ) -> QuotesResponse:
        quote_request = request or QuotesRequest()
        normalized_symbols = _normalize_symbols(
            symbols, override_symbol_count=quote_request.override_symbol_count is True
        )
        response = await self._transport.request(
            "GET",
            f"/v1/market/quote/{_quote_path(','.join(normalized_symbols))}.json",
            params=quote_request.query_params(),
            safety=RetrySafety.SAFE_READ,
            operation="market.quotes",
        )
        data = _require_mapping(response.data, "quote")
        quote_data = _unwrap(data, "QuoteResponse", "quote")
        try:
            return validate_response_shape(
                QuotesResponse.model_validate(quote_data), "quote", collection_field="quotes"
            )
        except ValidationError as error:
            raise_response_validation_error("Invalid quote response", error)

    async def lookup_product(self, search: str) -> ProductLookupResponse:
        lookup_request = ProductLookupRequest(search=search)
        response = await self._transport.request(
            "GET",
            f"/v1/market/lookup/{_quote_path(lookup_request.search)}.json",
            safety=RetrySafety.SAFE_READ,
            operation="market.lookup",
        )
        data = _require_mapping(response.data, "product lookup")
        lookup_data = _unwrap(data, "LookupResponse", "product lookup")
        try:
            return validate_response_shape(
                ProductLookupResponse.model_validate(lookup_data),
                "product lookup",
                collection_field="products",
            )
        except ValidationError as error:
            raise_response_validation_error("Invalid product lookup response", error)

    async def get_option_expirations(
        self, symbol: str, request: OptionExpirationsRequest | None = None
    ) -> OptionExpirationsResponse:
        normalized_symbol = _normalize_symbol(symbol)
        expirations_request = request or OptionExpirationsRequest()
        response = await self._transport.request(
            "GET",
            "/v1/market/optionexpiredate.json",
            params=expirations_request.query_params(normalized_symbol),
            safety=RetrySafety.SAFE_READ,
            operation="market.option_expirations",
        )
        data = _require_mapping(response.data, "option expirations")
        expirations_data = _unwrap(data, "OptionExpireDateResponse", "option expirations")
        try:
            return validate_response_shape(
                OptionExpirationsResponse.model_validate(expirations_data),
                "option expirations",
                collection_field="expiration_dates",
            )
        except ValidationError as error:
            raise_response_validation_error("Invalid option expirations response", error)

    async def get_option_chain(
        self, symbol: str, request: OptionChainRequest | None = None
    ) -> OptionChainResponse:
        normalized_symbol = _normalize_symbol(symbol)
        chain_request = request or OptionChainRequest()
        response = await self._transport.request(
            "GET",
            "/v1/market/optionchains.json",
            params=chain_request.query_params(normalized_symbol),
            safety=RetrySafety.SAFE_READ,
            operation="market.option_chain",
        )
        data = _require_mapping(response.data, "option chain")
        chain_data = _unwrap(data, "OptionChainResponse", "option chain")
        try:
            return validate_response_shape(
                OptionChainResponse.model_validate(chain_data),
                "option chain",
                collection_field="option_pairs",
            )
        except ValidationError as error:
            raise_response_validation_error("Invalid option chain response", error)


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not normalized:
        raise ETradeValidationError("symbol is required")
    return normalized


def _normalize_symbols(symbols: Sequence[str], *, override_symbol_count: bool) -> list[str]:
    if isinstance(symbols, str):
        raise ETradeValidationError("symbols must be a non-string sequence")
    normalized = [_normalize_symbol(symbol) for symbol in symbols]
    if not normalized:
        raise ETradeValidationError("at least one symbol is required")
    max_symbols = 50 if override_symbol_count else 25
    if len(normalized) > max_symbols:
        raise ETradeValidationError(f"at most {max_symbols} symbols are allowed")
    return normalized


def _quote_path(value: str) -> str:
    return quote(value, safe=",:")


def _require_mapping(data: JsonValue, response_name: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ETradeResponseError(f"Invalid {response_name} response")
    return cast(dict[str, Any], data)


def _unwrap(data: dict[str, Any], envelope: str, response_name: str) -> dict[str, Any]:
    value = data.get(envelope, data)
    if not isinstance(value, dict):
        raise ETradeResponseError(f"Invalid {response_name} response")
    return cast(dict[str, Any], value)
