from decimal import Decimal

import pytest

from etrade_python import (
    Account,
    AccountBalanceRequest,
    AccountBalanceResponse,
    AccountListResponse,
)


def test_account_preserves_broker_metadata() -> None:
    account = Account.model_validate(
        {
            "accountId": "123456",
            "accountIdKey": "fake-key",
            "accountMode": "MARGIN",
            "accountType": "INDIVIDUAL",
            "futureField": "kept",
        }
    )

    assert account.account_id == "123456"
    assert account.account_id_key == "fake-key"
    assert account.account_mode == "MARGIN"
    assert account.broker_metadata == {"futureField": "kept"}
    assert "futureField" not in account.model_dump()


def test_account_list_response_contains_accounts() -> None:
    response = AccountListResponse.model_validate(
        {"accounts": [{"accountId": "123456", "accountIdKey": "fake-key"}]}
    )

    assert len(response.accounts) == 1
    assert response.accounts[0].account_id == "123456"


def test_balance_request_query_params() -> None:
    request = AccountBalanceRequest(account_type="CASH", real_time_nav=True)

    assert request.query_params() == {
        "instType": "BROKERAGE",
        "accountType": "CASH",
        "realTimeNAV": True,
    }


def test_balance_request_rejects_blank_inst_type() -> None:
    with pytest.raises(ValueError, match="nonempty"):
        AccountBalanceRequest(inst_type=" ")


def test_balance_request_rejects_blank_account_type() -> None:
    with pytest.raises(ValueError, match="nonempty"):
        AccountBalanceRequest(account_type=" ")


def test_account_balance_decimal_and_nested_models() -> None:
    balance = AccountBalanceResponse.model_validate(
        {
            "accountId": "123456",
            "computedBalance": {
                "cashAvailableForInvestment": "12.34",
                "cashBalance": Decimal("56.78"),
                "realTimeValues": {"totalAccountValue": "100.01"},
                "portfolioMargin": {"totalMarginRqmts": "5.00"},
            },
            "openCalls": {"houseCall": "1.25"},
            "futureBalanceField": "kept",
        }
    )

    assert balance.computed_balance is not None
    assert balance.computed_balance.cash_available_for_investment == Decimal("12.34")
    assert balance.computed_balance.cash_balance == Decimal("56.78")
    assert balance.computed_balance.real_time_values is not None
    assert balance.computed_balance.real_time_values.total_account_value == Decimal("100.01")
    assert balance.open_calls[0].house_call == Decimal("1.25")
    assert balance.broker_metadata == {"futureBalanceField": "kept"}
