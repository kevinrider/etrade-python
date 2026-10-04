from datetime import date
from decimal import Decimal

import pytest

from etrade_python import OrderBuilder, PlaceOrderRequest, PreviewOrderRequest


def test_equity_limit_builder_creates_preview_and_place_requests() -> None:
    builder = (
        OrderBuilder.for_account("fake-account-key")
        .client_order_id("manual-test-001")
        .equity_limit("aapl", action="buy", quantity=1, limit_price=Decimal("1.00"))
    )

    preview = builder.build_preview_request()
    place = builder.build_place_request([123456789])

    assert isinstance(preview, PreviewOrderRequest)
    assert isinstance(place, PlaceOrderRequest)
    assert builder.account_id_key == "fake-account-key"
    assert preview.order_type == "EQ"
    assert preview.client_order_id == "manual-test-001"
    assert preview.orders[0].price_type == "LIMIT"
    assert preview.orders[0].limit_price == Decimal("1.00")
    assert preview.orders[0].instruments[0].product.symbol == "AAPL"
    assert preview.orders[0].instruments[0].order_action == "BUY"
    assert place.preview_ids[0].preview_id == 123456789
    assert place.request_body()["PlaceOrderRequest"]["PreviewIds"] == [{"previewId": 123456789}]


def test_long_call_limit_builder_creates_option_leg() -> None:
    preview = (
        OrderBuilder.for_account("fake-account-key")
        .client_order_id("manual-test-002")
        .long_call_limit(
            "spy",
            expiration=date(2026, 10, 16),
            strike_price="200",
            quantity="1",
            limit_price="2.00",
        )
        .build_preview_request()
    )

    product = preview.orders[0].instruments[0].product
    assert preview.order_type == "OPTN"
    assert product.security_type == "OPTN"
    assert product.symbol == "SPY"
    assert product.call_put == "CALL"
    assert product.expiry_year == 2026
    assert product.expiry_month == 10
    assert product.expiry_day == 16
    assert product.strike_price == Decimal("200")
    assert preview.orders[0].instruments[0].order_action == "BUY_OPEN"


def test_vertical_call_builder_creates_two_spread_legs() -> None:
    preview = (
        OrderBuilder.for_account("fake-account-key")
        .client_order_id("manual-test-003")
        .option_vertical_call(
            "SPY",
            expiration=date(2026, 10, 16),
            quantity=1,
            long_strike=180,
            short_strike=185,
            net_debit="2.00",
        )
        .build_preview_request()
    )

    detail = preview.orders[0]
    assert preview.order_type == "SPREADS"
    assert detail.price_type == "NET_DEBIT"
    assert detail.limit_price == Decimal("2.00")
    assert [leg.order_action for leg in detail.instruments] == ["BUY_OPEN", "SELL_OPEN"]
    assert [leg.product.strike_price for leg in detail.instruments] == [
        Decimal("180"),
        Decimal("185"),
    ]


def test_three_leg_builder_creates_call_spread_and_short_put() -> None:
    preview = (
        OrderBuilder.for_account("fake-account-key")
        .client_order_id("manual-test-004")
        .three_leg_call_spread_short_put(
            "SPY",
            expiration=date(2026, 10, 16),
            quantity=1,
            long_call_strike=180,
            short_call_strike=185,
            short_put_strike=120,
            net_debit="2.00",
        )
        .build_preview_request()
    )

    instruments = preview.orders[0].instruments
    assert len(instruments) == 3
    assert [leg.product.call_put for leg in instruments] == ["CALL", "CALL", "PUT"]
    assert [leg.order_action for leg in instruments] == [
        "BUY_OPEN",
        "SELL_OPEN",
        "SELL_OPEN",
    ]


def test_iron_condor_builder_creates_four_credit_spread_legs() -> None:
    preview = (
        OrderBuilder.for_account("fake-account-key")
        .client_order_id("manual-test-005")
        .iron_condor(
            "SPY",
            expiration=date(2026, 10, 16),
            quantity=1,
            short_put_strike=110,
            long_put_strike=105,
            short_call_strike=190,
            long_call_strike=195,
            net_credit="1.25",
        )
        .build_preview_request()
    )

    detail = preview.orders[0]
    assert detail.price_type == "NET_CREDIT"
    assert detail.limit_price == Decimal("1.25")
    assert [leg.product.call_put for leg in detail.instruments] == [
        "PUT",
        "PUT",
        "CALL",
        "CALL",
    ]
    assert [leg.order_action for leg in detail.instruments] == [
        "SELL_OPEN",
        "BUY_OPEN",
        "SELL_OPEN",
        "BUY_OPEN",
    ]


def test_buy_write_builder_creates_stock_and_covered_call_legs() -> None:
    preview = (
        OrderBuilder.for_account("fake-account-key")
        .client_order_id("manual-test-006")
        .buy_write(
            "SPY",
            expiration=date(2026, 10, 16),
            stock_quantity=100,
            call_quantity=1,
            call_strike=210,
            net_debit="200.00",
        )
        .build_preview_request()
    )

    detail = preview.orders[0]
    assert preview.order_type == "BUY_WRITES"
    assert detail.price_type == "NET_DEBIT"
    assert [leg.product.security_type for leg in detail.instruments] == ["EQ", "OPTN"]
    assert [leg.order_action for leg in detail.instruments] == ["BUY", "SELL_OPEN"]
    assert detail.instruments[0].quantity == Decimal("100")


def test_builder_can_build_change_requests() -> None:
    builder = (
        OrderBuilder.for_account("fake-account-key")
        .client_order_id("manual-test-007")
        .equity_limit("AAPL", action="BUY", quantity=1, limit_price="1.00")
    )

    preview = builder.build_change_preview_request(order_id=456)
    place = builder.build_change_place_request([{"previewId": 123}], order_id=456)

    assert builder.order_id == 456
    assert preview.client_order_id == "manual-test-007"
    assert place.preview_ids[0].preview_id == 123


def test_builder_validates_required_state() -> None:
    with pytest.raises(ValueError, match="account_id_key"):
        OrderBuilder.for_account(" ")

    with pytest.raises(ValueError, match="client_order_id"):
        OrderBuilder.for_account("fake-account-key").equity_limit(
            "AAPL", action="BUY", quantity=1, limit_price="1.00"
        ).build_preview_request()

    with pytest.raises(ValueError, match="expiration"):
        (
            OrderBuilder.for_account("fake-account-key")
            .client_order_id("manual-test-008")
            .order_type("OPTN")
            .with_symbol("SPY")
            .limit("1.00")
            .add_long_call("200")
        )

    with pytest.raises(ValueError, match="preview ID"):
        (
            OrderBuilder.for_account("fake-account-key")
            .client_order_id("manual-test-009")
            .equity_limit("AAPL", action="BUY", quantity=1, limit_price="1.00")
            .build_place_request([])
        )

    with pytest.raises(ValueError, match="positive"):
        (
            OrderBuilder.for_account("fake-account-key")
            .client_order_id("manual-test-010")
            .equity_limit("AAPL", action="BUY", quantity=0, limit_price="1.00")
        )


def test_builder_low_level_fluent_methods() -> None:
    market_preview = (
        OrderBuilder.for_account("fake-account-key")
        .client_order_id("manual-test-011")
        .order_type("EQ")
        .with_symbol("MSFT")
        .quantity_type("quantity")
        .gtc()
        .market()
        .market_session("extended")
        .all_or_none(True)
        .add_equity("sell", 2, symbol="MSFT")
        .build_preview_request()
    )

    market_detail = market_preview.orders[0]
    assert market_detail.price_type == "MARKET"
    assert market_detail.order_term == "GOOD_UNTIL_CANCEL"
    assert market_detail.market_session == "EXTENDED"
    assert market_detail.all_or_none is True
    assert market_detail.limit_price is None
    assert market_detail.instruments[0].quantity_type == "QUANTITY"
    assert market_detail.instruments[0].order_action == "SELL"

    stop_preview = (
        OrderBuilder.for_account("fake-account-key")
        .client_order_id("manual-test-012")
        .order_type("EQ")
        .with_symbol("MSFT")
        .stop("90")
        .add_equity("SELL", 1)
        .build_preview_request()
    )
    assert stop_preview.orders[0].price_type == "STOP"
    assert stop_preview.orders[0].stop_price == Decimal("90")

    stop_limit_preview = (
        OrderBuilder.for_account("fake-account-key")
        .client_order_id("manual-test-013")
        .order_type("EQ")
        .with_symbol("MSFT")
        .stop_limit("90", "89")
        .add_equity("SELL", 1)
        .build_preview_request()
    )
    assert stop_limit_preview.orders[0].price_type == "STOP_LIMIT"
    assert stop_limit_preview.orders[0].stop_limit_price == Decimal("89")


@pytest.mark.parametrize(
    ("builder", "message"),
    [
        (OrderBuilder.for_account("fake-account-key").client_order_id("x"), "order_type"),
        (
            OrderBuilder.for_account("fake-account-key").client_order_id("x").order_type("EQ"),
            "price_type",
        ),
        (
            OrderBuilder.for_account("fake-account-key")
            .client_order_id("x")
            .order_type("EQ")
            .price_type("LIMIT"),
            "instrument",
        ),
    ],
)
def test_builder_validates_missing_preview_state(builder: OrderBuilder, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        builder.build_preview_request()


def test_builder_validates_change_order_ids() -> None:
    builder = (
        OrderBuilder.for_account("fake-account-key")
        .client_order_id("manual-test-014")
        .equity_limit("AAPL", action="BUY", quantity=1, limit_price="1.00")
    )

    with pytest.raises(ValueError, match="order_id"):
        builder.order_id_for_change(0)
    with pytest.raises(ValueError, match="order_id"):
        builder.build_change_preview_request()
    with pytest.raises(ValueError, match="order_id"):
        builder.build_change_place_request([123])


def test_builder_validates_preview_id_shapes() -> None:
    builder = (
        OrderBuilder.for_account("fake-account-key")
        .client_order_id("manual-test-015")
        .equity_limit("AAPL", action="BUY", quantity=1, limit_price="1.00")
    )

    with pytest.raises(ValueError, match="preview IDs"):
        builder.build_place_request([False])
    with pytest.raises(ValueError, match="preview IDs"):
        builder.build_place_request([0])
    with pytest.raises(ValueError, match="preview IDs"):
        builder.build_place_request([{"previewId": False}])
    with pytest.raises(ValueError, match="preview IDs"):
        builder.build_place_request([{"previewId": -1}])


def test_builder_validates_symbols_and_decimal_values() -> None:
    with pytest.raises(ValueError, match="symbol"):
        (
            OrderBuilder.for_account("fake-account-key")
            .client_order_id("manual-test-016")
            .order_type("EQ")
            .limit("1.00")
            .add_equity("BUY", 1)
        )

    with pytest.raises(ValueError, match="decimal"):
        (
            OrderBuilder.for_account("fake-account-key")
            .client_order_id("manual-test-017")
            .equity_limit("AAPL", action="BUY", quantity=1, limit_price="not-a-number")
        )

    with pytest.raises(ValueError, match="finite"):
        (
            OrderBuilder.for_account("fake-account-key")
            .client_order_id("manual-test-018")
            .equity_limit("AAPL", action="BUY", quantity=1, limit_price="NaN")
        )
