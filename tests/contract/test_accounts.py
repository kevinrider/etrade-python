from decimal import Decimal

import httpx
import pytest

from etrade_python import (
    Account,
    AccountBalanceRequest,
    AccountListResponse,
    ETradeClient,
    ETradeResponseError,
    ETradeSettings,
    ETradeValidationError,
)
from etrade_python.accounts import AccountsService
from etrade_python.transport import ApiTransport
from tests.conftest import FakeAuthenticator


async def test_accounts_list_contract(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.method == "GET"
        assert request.url.path == "/v1/accounts/list.json"
        assert request.headers["Authorization"].startswith("OAuth ")
        return httpx.Response(
            200,
            json={
                "AccountListResponse": {
                    "accounts": {
                        "account": [
                            {
                                "accountId": "840104290",
                                "accountIdKey": "JIdOIAcSpwR1Jva7RQBraQ",
                                "accountMode": "MARGIN",
                                "accountDesc": "INDIVIDUAL",
                                "accountName": "Individual Brokerage",
                                "accountType": "INDIVIDUAL",
                                "institutionType": "BROKERAGE",
                                "accountStatus": "ACTIVE",
                                "closedDate": 0,
                                "newBrokerField": "kept",
                            }
                        ]
                    }
                }
            },
        )

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        response = await AccountsService(transport).list()

    assert len(seen) == 1
    assert auth.calls == 1
    assert response == AccountListResponse(
        accounts=[
            Account.model_validate(
                {
                    "accountId": "840104290",
                    "accountIdKey": "JIdOIAcSpwR1Jva7RQBraQ",
                    "accountMode": "MARGIN",
                    "accountDesc": "INDIVIDUAL",
                    "accountName": "Individual Brokerage",
                    "accountType": "INDIVIDUAL",
                    "institutionType": "BROKERAGE",
                    "accountStatus": "ACTIVE",
                    "closedDate": 0,
                    "newBrokerField": "kept",
                }
            )
        ]
    )


async def test_accounts_list_204_is_empty(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(lambda r: httpx.Response(204)),
    ) as transport:
        response = await AccountsService(transport).list()

    assert response == AccountListResponse(accounts=[])


async def test_accounts_list_retries_safe_reads(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, headers={"Retry-After": "0"})
        return httpx.Response(
            200,
            json={
                "AccountListResponse": {
                    "accounts": {"account": {"accountId": "123456", "accountIdKey": "account-key"}}
                }
            },
        )

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(handler),
        sleep=sleep,
    ) as transport:
        response = await AccountsService(transport).list()

    assert len(response.accounts) == 1
    assert calls == 2
    assert auth.calls == 2
    assert delays == [0]


async def test_get_balance_contract(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/accounts/fake-account-key/balance.json"
        assert request.url.params == httpx.QueryParams(
            {"instType": "BROKERAGE", "accountType": "CASH", "realTimeNAV": "true"}
        )
        return httpx.Response(
            200,
            json={
                "BalanceResponse": {
                    "accountId": "835649790",
                    "accountType": "PDT_ACCOUNT",
                    "optionLevel": "LEVEL_4",
                    "accountDescription": "Individual Brokerage",
                    "quoteMode": 6,
                    "Cash": {
                        "fundsForOpenOrdersCash": 0,
                        "moneyMktBalance": 0,
                    },
                    "Computed": {
                        "cashAvailableForInvestment": "0",
                        "netCash": "93921.44",
                        "cashBalance": "93921.44",
                        "cashBuyingPower": "93921.44",
                    },
                    "Margin": {
                        "dtCashOpenOrderReserve": 0,
                        "dtMarginOpenOrderReserve": 0,
                    },
                }
            },
        )

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        balance = await AccountsService(transport).get_balance(
            "fake-account-key",
            AccountBalanceRequest(account_type="CASH", real_time_nav=True),
        )

    assert balance.account_id == "835649790"
    assert balance.cash is not None
    assert balance.cash.money_market_balance == Decimal("0")
    assert balance.computed_balance is not None
    assert balance.computed_balance.net_cash == Decimal("93921.44")
    assert balance.margin is not None
    assert balance.margin.dt_margin_open_order_reserve == Decimal("0")


async def test_get_balance_rejects_blank_account_id(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ApiTransport(settings, authenticator=auth) as transport:
        with pytest.raises(ETradeValidationError, match="account_id_key"):
            await AccountsService(transport).get_balance(" ")


async def test_invalid_account_response_is_structured(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"bad": True})),
    ) as transport:
        with pytest.raises(ETradeResponseError):
            await AccountsService(transport).list()


async def test_client_exposes_accounts_service(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ETradeClient(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(lambda r: httpx.Response(204)),
    ) as client:
        assert isinstance(client.accounts, AccountsService)
        response = await client.accounts.list()

    assert response == AccountListResponse(accounts=[])
