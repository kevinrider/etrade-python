"""HTTP contracts for complete documented response structures."""

from datetime import UTC, date, datetime
from decimal import Decimal

import httpx

from etrade_python import (
    ETradeClient,
    ETradeSettings,
    MutualFundQuoteDetails,
    PlaceOrderRequest,
    PreviewOrderRequest,
)
from tests.conftest import FakeAuthenticator, load_json_fixture


async def test_complete_portfolio_response(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ETradeClient(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json=load_json_fixture("responses/portfolio_complete_response.json")
            )
        ),
    ) as client:
        response = await client.portfolio.get_positions("fake-account")

    position = response.account_portfolios[0].positions[0]
    assert position.quote_status == "REALTIME"
    assert position.today_commissions == Decimal("12.345")
    assert position.broker_metadata == {"futurePositionField": "preserved"}
    complete = position.complete
    assert complete is not None
    assert complete.gamma == Decimal("12.345")
    assert complete.market_cap == Decimal("12.345")
    assert complete.bid_size == 7
    assert complete.options_adjusted_flag is True
    assert complete.div_pay_date == date(2018, 3, 21)
    assert complete.broker_metadata == {"futureCompleteField": "preserved"}
    serialized = response.model_dump(mode="json", by_alias=True)
    assert serialized["accountPortfolio"][0]["position"][0]["complete"]["gamma"] == "12.345"


async def test_complete_quote_response(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    async with ETradeClient(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json=load_json_fixture("responses/quote_details_response.json")
            )
        ),
    ) as client:
        response = await client.market.get_quotes(["EXAMPLE"])

    quote = response.quotes[0]
    assert quote.broker_metadata == {"futureQuoteField": "preserved"}
    assert response.messages is not None
    assert response.messages.messages[0].code == 0
    assert quote.all is not None
    assert quote.all.option_deliverables[0].deliverable_whole_shares == 7
    assert quote.all.eh_quote is not None
    assert quote.all.eh_quote.bid_size == 7
    assert quote.all.eh_quote.last_price == Decimal("12.345")
    assert quote.all.eh_quote.time_of_last_trade == datetime(2018, 3, 21, 18, 40, tzinfo=UTC)
    assert quote.option is not None
    assert quote.option.option_greeks is not None
    assert quote.option.option_greeks.delta == Decimal("12.345")
    fund = quote.mutual_fund
    assert isinstance(fund, MutualFundQuoteDetails)
    assert fund.initial_investment == Decimal("12.345")
    assert fund.order_cutoff_time == datetime(2018, 3, 21, 18, 40, tzinfo=UTC)
    assert fund.performance_as_of_date == datetime(2018, 3, 21, tzinfo=UTC)
    assert fund.broker_metadata == {"futureFundField": "preserved"}
    assert fund.net_assets is not None
    assert fund.net_assets.value == Decimal("12.345")
    assert fund.net_assets.broker_metadata == {"futureAssetField": "preserved"}
    assert fund.redemption is not None
    assert fund.redemption.sales_values[0].percent == "example"
    assert fund.front_end_sales_charges[0].percent == "example"
    serialized = response.model_dump(mode="json", by_alias=True)
    assert serialized["quoteData"][0]["option"]["optionGreeks"]["delta"] == "12.345"


async def test_complete_order_responses(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            name = "orders_response_full.json"
        elif request.url.path.endswith("/preview.json"):
            name = "preview_order_response_full.json"
        else:
            name = "place_order_response_full.json"
        return httpx.Response(200, json=load_json_fixture(f"responses/{name}"))

    preview_request = PreviewOrderRequest.model_validate(
        load_json_fixture("responses/preview_order_request_equity.json")["PreviewOrderRequest"]
    )
    place_request = PlaceOrderRequest.model_validate(
        load_json_fixture("responses/place_order_request_equity.json")["PlaceOrderRequest"]
    )
    async with ETradeClient(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as client:
        listed = await client.orders.list("fake-account")
        preview = await client.orders.preview("fake-account", preview_request)
        placed = await client.orders.place("fake-account", place_request)

    assert listed.orders[0].order_details[0].bracketed_limit_price == Decimal("12.345")
    assert preview.total_commission == Decimal("12.345")
    assert preview.message_list is not None
    assert preview.message_list.messages[0].code == 0
    assert preview.portfolio_margin is not None
    assert preview.portfolio_margin.pm_eligible is True
    assert preview.cash_bp_details is not None
    assert preview.cash_bp_details.settled is not None
    assert preview.cash_bp_details.settled.net_bp == Decimal("12.345")
    assert preview.margin_bp_details is not None
    assert preview.margin_bp_details.marginable is not None
    assert preview.margin_bp_details.marginable.broker_metadata == {
        "futureBuyingPowerField": "preserved"
    }
    assert preview.dt_bp_details is not None
    assert preview.dt_bp_details.non_marginable is not None
    assert preview.dt_bp_details.non_marginable.current_order_impact == Decimal("12.345")
    assert preview.preview_ids[0].cash_margin == "example"
    assert preview.broker_metadata == {"futureOrderField": "preserved"}
    assert placed.total_order_value == Decimal("12.345")
    assert placed.commission_msg == "example"
    assert placed.message_list is not None
    assert placed.message_list.messages[0].code == 0
    assert placed.disclosure is not None
    assert placed.disclosure.ah_disclosure_flag is True
    assert placed.order_ids[0].cash_margin == "example"
    assert placed.orders[0].instruments[0].mf_transaction == "example"
    assert placed.broker_metadata == {"futureOrderField": "preserved"}
    serialized = preview.model_dump(mode="json", by_alias=True)
    assert serialized["cashBpDetails"]["settled"]["netBp"] == "12.345"
