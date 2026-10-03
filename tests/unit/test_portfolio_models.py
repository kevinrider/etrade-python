from decimal import Decimal

import pytest

from etrade_python import PortfolioRequest, PortfolioResponse


def test_portfolio_request_query_params() -> None:
    request = PortfolioRequest(
        count=25,
        sort_by="SYMBOL",
        sort_order="ASC",
        page_number=2,
        market_session="REGULAR",
        totals_required=True,
        lots_required=False,
        view="QUICK",
    )

    assert request.query_params() == {
        "count": 25,
        "sortBy": "SYMBOL",
        "sortOrder": "ASC",
        "pageNumber": 2,
        "marketSession": "REGULAR",
        "totalsRequired": "true",
        "lotsRequired": "false",
        "view": "QUICK",
    }


def test_portfolio_request_rejects_blank_strings() -> None:
    with pytest.raises(ValueError, match="nonempty"):
        PortfolioRequest(view=" ")


def test_portfolio_response_parses_nested_aliases_and_decimals() -> None:
    response = PortfolioResponse.model_validate(
        {
            "Totals": {"totalMarketValue": "100.25"},
            "AccountPortfolio": {
                "accountId": "123456",
                "Position": {
                    "positionId": 100,
                    "Product": {"symbol": "AAPL", "securityType": "EQ"},
                    "quantity": "2",
                    "marketValue": "350.50",
                    "Quick": {"lastTrade": "175.25"},
                    "PositionLot": {"positionLotId": 1, "remainingQty": "2"},
                    "futureField": "kept",
                },
            },
        }
    )

    assert response.totals is not None
    assert response.totals.total_market_value == Decimal("100.25")
    account = response.account_portfolios[0]
    position = account.positions[0]
    assert position.product is not None
    assert position.product.symbol == "AAPL"
    assert position.quantity == Decimal("2")
    assert position.market_value == Decimal("350.50")
    assert position.quick is not None
    assert position.quick.last_trade == Decimal("175.25")
    assert position.position_lots[0].remaining_qty == Decimal("2")
    assert position.broker_metadata == {"futureField": "kept"}
