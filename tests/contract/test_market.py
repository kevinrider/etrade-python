from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from etrade_python import (
    ETradeClient,
    ETradeResponseError,
    ETradeSettings,
    ETradeValidationError,
    OptionChainRequest,
    OptionExpirationsRequest,
    QuotesRequest,
)
from etrade_python.market import MarketService
from etrade_python.transport import ApiTransport
from tests.conftest import FakeAuthenticator, load_json_fixture


async def test_get_quote_contract(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/market/quote/GOOG.json"
        assert request.url.params == httpx.QueryParams(
            {"detailFlag": "ALL", "requireEarningsDate": "true"}
        )
        return httpx.Response(200, json=load_json_fixture("responses/quote_response.json"))

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        quote = await MarketService(transport).get_quote(
            "goog", QuotesRequest(detail_flag="all", require_earnings_date=True)
        )

    assert quote.product is not None
    assert quote.product.symbol == "GOOG"
    assert quote.date_time_utc == datetime(2018, 6, 20, 19, 17, tzinfo=UTC)
    assert quote.all is not None
    assert quote.all.last_trade == Decimal("1175.74")


async def test_get_quotes_contract(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/market/quote/GOOG,AAPL.json"
        assert request.url.params == httpx.QueryParams({"overrideSymbolCount": "true"})
        return httpx.Response(200, json=load_json_fixture("responses/quote_response.json"))

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        response = await MarketService(transport).get_quotes(
            ["goog", "aapl"], QuotesRequest(override_symbol_count=True)
        )

    assert len(response.quotes) == 1


async def test_product_lookup_contract(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/market/lookup/a.json"
        return httpx.Response(200, json=load_json_fixture("responses/product_lookup_response.json"))

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        response = await MarketService(transport).lookup_product("a")

    assert len(response.products) == 3
    assert response.products[0].description == "AGILENT TECHNOLOGIES INC COM"


async def test_option_expirations_contract(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/market/optionexpiredate.json"
        assert request.url.params == httpx.QueryParams({"symbol": "GOOG", "expiryType": "ALL"})
        return httpx.Response(
            200, json=load_json_fixture("responses/option_expirations_response.json")
        )

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        response = await MarketService(transport).get_option_expirations(
            "goog", OptionExpirationsRequest(expiry_type="all")
        )

    assert len(response.expiration_dates) == 3
    assert response.expiration_dates[0].month == 6


async def test_option_chain_contract(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/market/optionchains.json"
        assert request.url.params == httpx.QueryParams(
            {
                "symbol": "IBM",
                "expiryYear": "2018",
                "expiryMonth": "8",
                "strikePriceNear": "200",
                "noOfStrikes": "2",
                "chainType": "CALLPUT",
            }
        )
        return httpx.Response(200, json=load_json_fixture("responses/option_chain_response.json"))

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        response = await MarketService(transport).get_option_chain(
            "ibm",
            OptionChainRequest(
                expiry_year=2018,
                expiry_month=8,
                strike_price_near=Decimal("200"),
                no_of_strikes=2,
                chain_type="callput",
            ),
        )

    assert response.quote_type == "DELAYED"
    assert len(response.option_pairs) == 2
    assert response.option_pairs[0].call is not None
    assert response.option_pairs[0].call.ask == Decimal("0.05")


async def test_market_rejects_blank_symbol(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ApiTransport(settings, authenticator=auth) as transport:
        service = MarketService(transport)
        with pytest.raises(ETradeValidationError, match="symbol"):
            await service.get_quote(" ")
        with pytest.raises(ETradeValidationError, match="symbol"):
            await service.get_option_chain(" ")
        with pytest.raises(ETradeValidationError, match="symbol"):
            await service.get_quotes([])


async def test_invalid_market_responses_are_structured(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])),
    ) as transport:
        with pytest.raises(ETradeResponseError):
            await MarketService(transport).lookup_product("a")


async def test_client_exposes_market_service(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ETradeClient(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json=load_json_fixture("responses/quote_response.json"))
        ),
    ) as client:
        assert isinstance(client.market, MarketService)
        quote = await client.market.get_quote("GOOG")

    assert quote.product is not None
    assert quote.product.symbol == "GOOG"
