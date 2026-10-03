from datetime import UTC, datetime
from decimal import Decimal

import pytest

from etrade_python import (
    OptionChainRequest,
    OptionExpirationsRequest,
    ProductLookupRequest,
    QuotesRequest,
    QuotesResponse,
)
from etrade_python.market import (
    OptionChainResponse,
    OptionExpirationsResponse,
    ProductLookupResponse,
)
from tests.conftest import load_json_fixture


def test_quotes_request_query_params() -> None:
    request = QuotesRequest(
        detail_flag="all",
        require_earnings_date=True,
        override_symbol_count=False,
        skip_mini_options_check=True,
    )

    assert request.query_params() == {
        "detailFlag": "ALL",
        "requireEarningsDate": "true",
        "overrideSymbolCount": "false",
        "skipMiniOptionsCheck": "true",
    }


def test_quotes_request_rejects_invalid_detail_flag() -> None:
    with pytest.raises(ValueError, match="detail flag"):
        QuotesRequest(detail_flag="bad")


def test_product_lookup_request_rejects_blank_search() -> None:
    with pytest.raises(ValueError, match="nonempty"):
        ProductLookupRequest(search=" ")


def test_option_expirations_request_query_params() -> None:
    request = OptionExpirationsRequest(expiry_type="all")

    assert request.query_params("GOOG") == {"symbol": "GOOG", "expiryType": "ALL"}


def test_option_chain_request_query_params() -> None:
    request = OptionChainRequest(
        expiry_year=2018,
        expiry_month=8,
        expiry_day=17,
        strike_price_near=Decimal("200"),
        no_of_strikes=2,
        include_weekly=True,
        skip_adjusted=False,
        option_category="standard",
        chain_type="callput",
        price_type="all",
    )

    assert request.query_params("IBM") == {
        "symbol": "IBM",
        "expiryYear": 2018,
        "expiryMonth": 8,
        "expiryDay": 17,
        "strikePriceNear": "200",
        "noOfStrikes": 2,
        "includeWeekly": "true",
        "skipAdjusted": "false",
        "optionCategory": "STANDARD",
        "chainType": "CALLPUT",
        "priceType": "ALL",
    }


def test_quote_response_parses_fixture() -> None:
    response = QuotesResponse.model_validate(
        load_json_fixture("responses/quote_response.json")["QuoteResponse"]
    )

    quote = response.quotes[0]
    assert quote.date_time == datetime(2018, 6, 20, 19, 17, tzinfo=UTC)
    assert quote.date_time_utc == datetime(2018, 6, 20, 19, 17, tzinfo=UTC)
    assert quote.product is not None
    assert quote.product.symbol == "GOOG"
    assert quote.all is not None
    assert quote.all.last_trade == Decimal("1175.74")
    assert quote.all.time_of_last_trade == datetime(2018, 6, 20, 19, 17, tzinfo=UTC)


def test_product_lookup_response_parses_fixture() -> None:
    response = ProductLookupResponse.model_validate(
        load_json_fixture("responses/product_lookup_response.json")["LookupResponse"]
    )

    assert len(response.products) == 3
    assert response.products[0].symbol == "A"


def test_option_expirations_response_parses_fixture() -> None:
    response = OptionExpirationsResponse.model_validate(
        load_json_fixture("responses/option_expirations_response.json")["OptionExpireDateResponse"]
    )

    assert response.expiration_dates[0].year == 2018
    assert response.expiration_dates[0].expiry_type == "WEEKLY"


def test_option_chain_response_parses_fixture() -> None:
    response = OptionChainResponse.model_validate(
        load_json_fixture("responses/option_chain_response.json")["OptionChainResponse"]
    )

    assert response.quote_type == "DELAYED"
    assert response.near_price == Decimal("200.0")
    assert response.selected is not None
    assert response.selected.year == 2018
    first_pair = response.option_pairs[0]
    assert first_pair.call is not None
    assert first_pair.call.option_type == "CALL"
    assert first_pair.call.option_greek is not None
    assert first_pair.call.option_greek.delta == Decimal("0.004900")
    assert first_pair.put is not None
    assert first_pair.put.option_type == "PUT"
