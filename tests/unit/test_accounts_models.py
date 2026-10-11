from datetime import date
from decimal import Decimal

import pytest

from etrade_python import (
    Account,
    AccountBalanceRequest,
    AccountBalanceResponse,
    AccountListResponse,
)


def test_account_discards_unknown_fields() -> None:
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
    assert not hasattr(account, "futureField")
    assert "futureField" not in account.model_dump(by_alias=True)
    assert "futureField" not in account.model_dump()


def test_account_closed_date_uses_date_and_zero_is_none() -> None:
    active_account = Account.model_validate(
        {"accountId": "123456", "accountIdKey": "fake-key", "closedDate": 0}
    )
    closed_account = Account.model_validate(
        {"accountId": "123456", "accountIdKey": "fake-key", "closedDate": 20261003}
    )

    assert active_account.closed_date is None
    assert closed_account.closed_date == date(2026, 10, 3)


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
            "asOfDate": 20261003,
            "computedBalance": {
                "cashAvailableForInvestment": "12.34",
                "cashBalance": Decimal("56.78"),
                "realTimeValues": {"totalAccountValue": "100.01"},
                "portfolioMargin": {"totalMarginRqmts": "5.00"},
            },
            "openCalls": {"houseCall": "1.25"},
            "lending": {"paymentDueDate": 20261004, "lastPaymentReceivedDate": 20261001},
            "futureBalanceField": "kept",
        }
    )

    assert balance.computed_balance is not None
    assert balance.computed_balance.cash_available_for_investment == Decimal("12.34")
    assert balance.computed_balance.cash_balance == Decimal("56.78")
    assert balance.computed_balance.real_time_values is not None
    assert balance.computed_balance.real_time_values.total_account_value == Decimal("100.01")
    assert balance.open_calls[0].house_call == Decimal("1.25")
    assert balance.as_of_date == date(2026, 10, 3)
    assert balance.lending is not None
    assert balance.lending.payment_due_date == date(2026, 10, 4)
    assert balance.lending.last_payment_received_date == date(2026, 10, 1)
    assert not hasattr(balance, "futureBalanceField")
    assert "futureBalanceField" not in balance.model_dump(by_alias=True)
