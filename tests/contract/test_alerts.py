import httpx
import pytest

from etrade_python import (
    AlertDetailsRequest,
    AlertsRequest,
    AlertsService,
    ETradeClient,
    ETradeResponseError,
    ETradeSettings,
    ETradeValidationError,
)
from etrade_python.transport import ApiTransport
from tests.conftest import FakeAuthenticator, load_json_fixture


async def test_list_alerts_contract(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/user/alerts.json"
        assert request.url.params == httpx.QueryParams(
            {
                "count": "10",
                "category": "STOCK",
                "status": "UNREAD",
                "direction": "DESC",
                "search": "AAPL",
            }
        )
        return httpx.Response(200, json=load_json_fixture("responses/alerts_response.json"))

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        response = await AlertsService(transport).list(
            AlertsRequest(
                count=10, category="stock", status="unread", direction="desc", search="AAPL"
            )
        )

    assert response.total_alerts == 148
    assert response.alerts[0].id == 6774


async def test_list_alerts_no_alerts_404_returns_empty(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(
            404,
            json={"Error": {"code": 53, "message": "There are currently no alerts in your inbox."}},
        )

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        response = await AlertsService(transport).list()

    assert response.total_alerts == 0
    assert response.alerts == []


async def test_list_alerts_no_alerts_404_message_returns_empty(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(
            lambda r: httpx.Response(
                404,
                json={"Error": {"message": "There are currently no alerts in your inbox."}},
            )
        ),
    ) as transport:
        response = await AlertsService(transport).list()

    assert response.alerts == []


async def test_alerts_invalid_responses_are_structured(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])),
    ) as transport:
        service = AlertsService(transport)
        with pytest.raises(ETradeResponseError, match="alerts"):
            await service.list()
        with pytest.raises(ETradeResponseError, match="alert details"):
            await service.get(1)
        with pytest.raises(ETradeResponseError, match="delete alerts"):
            await service.delete(1)


async def test_alerts_invalid_envelopes_are_structured(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ApiTransport(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"AlertsResponse": []})
        ),
    ) as transport:
        with pytest.raises(ETradeResponseError, match="alerts"):
            await AlertsService(transport).list()


async def test_alerts_reject_bool_and_string_delete_ids(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ApiTransport(settings, authenticator=auth) as transport:
        service = AlertsService(transport)
        with pytest.raises(ETradeValidationError, match="integers"):
            await service.delete(True)
        with pytest.raises(ETradeValidationError, match="integers"):
            await service.delete("1")  # type: ignore[arg-type]


async def test_get_alert_contract(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/user/alerts/6773.json"
        assert request.url.params == httpx.QueryParams({"htmlTags": "true"})
        return httpx.Response(200, json=load_json_fixture("responses/alert_details_response.json"))

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        response = await AlertsService(transport).get(6773, AlertDetailsRequest(htmlTags=True))

    assert response.id == 6773
    assert response.symbol == "AAPL"


async def test_delete_alerts_contract(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/v1/user/alerts/6772,6774.json"
        return httpx.Response(200, json=load_json_fixture("responses/delete_alerts_response.json"))

    async with ApiTransport(
        settings, authenticator=auth, http_transport=httpx.MockTransport(handler)
    ) as transport:
        response = await AlertsService(transport).delete([6772, 6774])

    assert response.result == "SUCCESS"


async def test_alerts_reject_invalid_ids(settings: ETradeSettings, auth: FakeAuthenticator) -> None:
    async with ApiTransport(settings, authenticator=auth) as transport:
        service = AlertsService(transport)
        with pytest.raises(ETradeValidationError, match="alert_id"):
            await service.get(0)
        with pytest.raises(ETradeValidationError, match="alert_id"):
            await service.delete([1, 0])
        with pytest.raises(ETradeValidationError, match="at least one"):
            await service.delete([])


async def test_client_exposes_alerts_service(
    settings: ETradeSettings, auth: FakeAuthenticator
) -> None:
    async with ETradeClient(
        settings,
        authenticator=auth,
        http_transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json=load_json_fixture("responses/alerts_response.json"))
        ),
    ) as client:
        assert isinstance(client.alerts, AlertsService)
        response = await client.alerts.list()

    assert response.alerts[0].id == 6774
