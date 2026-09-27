from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from etrade_python import (
    ETradeApiError,
    ETradeAuthenticationError,
    ETradeHttpAuthenticationError,
    ETradeNotFoundError,
    ETradeRateLimitError,
    ETradeResponseError,
    ETradeUnavailableError,
)
from etrade_python.transport.response import Redactor, parse_response


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (400, ETradeApiError),
        (401, ETradeHttpAuthenticationError),
        (403, ETradeHttpAuthenticationError),
        (404, ETradeNotFoundError),
        (429, ETradeRateLimitError),
        (500, ETradeUnavailableError),
        (302, ETradeApiError),
    ],
)
@pytest.mark.parametrize("format", ["json", "xml"])
def test_error_contract(status: int, error_type: type[ETradeApiError], format: str) -> None:
    content = (Path(__file__).parents[1] / "fixtures" / f"error.{format}").read_bytes()
    response = httpx.Response(status, content=content, headers={"X-Request-ID": "fake-request-id"})
    with pytest.raises(error_type) as exc:
        parse_response(response, Redactor([]))
    assert exc.value.status_code == status
    assert exc.value.broker_code == "100"
    assert exc.value.broker_message == "The example request could not be completed."
    assert exc.value.request_id == "fake-request-id"
    assert not hasattr(exc.value, "request")
    if status in {401, 403}:
        assert isinstance(exc.value, ETradeAuthenticationError)


@pytest.mark.parametrize(
    "body",
    [
        b"<html>fake-sensitive-data</html>",
        b"garbage",
        b"[]",
        b'{"Error": []}',
        b'{"code": [], "message": {}}',
        b"x" * 65537,
        b'<!DOCTYPE Error [<!ENTITY x "secret">]><Error><message>&x;</message></Error>',
        "<Error><message>secret</message></Error>".encode("utf-16"),
    ],
)
def test_unrecognized_errors_are_not_echoed(body: bytes) -> None:
    with pytest.raises(ETradeApiError) as exc:
        parse_response(httpx.Response(400, content=body), Redactor([]))
    assert exc.value.broker_message is None
    assert exc.value.broker_code is None
    assert str(exc.value) == "E*TRADE request failed (HTTP 400)"


def test_namespaced_xml_error() -> None:
    response = httpx.Response(400, content=b'<Error xmlns="urn:example"><code>42</code></Error>')
    with pytest.raises(ETradeApiError) as exc:
        parse_response(response, Redactor([]))
    assert exc.value.broker_code == "42"


def test_precision_and_no_content() -> None:
    result = parse_response(
        httpx.Response(
            200,
            content=b'{"amount":1234567890.123456789}',
            headers={"Content-Type": "application/json; charset=utf-8"},
        ),
        Redactor([]),
    )
    assert result.data == {"amount": Decimal("1234567890.123456789")}
    assert "amount" not in repr(result)
    assert parse_response(httpx.Response(204), Redactor([])).data is None
    assert (
        parse_response(
            httpx.Response(200, content=b"[]", headers={"Content-Type": "application/vendor+json"}),
            Redactor([]),
        ).data
        == []
    )


@pytest.mark.parametrize("content", [b"", b"{", b'{"x":NaN}', b'{"x":Infinity}', b"\xff"])
def test_invalid_success(content: bytes) -> None:
    with pytest.raises(ETradeResponseError, match="Invalid JSON"):
        parse_response(
            httpx.Response(200, content=content, headers={"Content-Type": "application/json"}),
            Redactor([]),
        )


def test_wrong_media_type() -> None:
    with pytest.raises(ETradeResponseError, match="Expected a JSON"):
        parse_response(httpx.Response(200, text="<xml/>"), Redactor([]))


def test_redaction_variants() -> None:
    redactor = Redactor(["fake/secret+=", "", "fake-key"])
    assert "fake" not in redactor.clean("fake/secret+= fake%2Fsecret%2B%3D fake-key")
    assert redactor.clean("oauth_token=unknown") == "oauth_token=[REDACTED]"
    assert redactor.clean('OAuth oauth_token="unknown"') == "[REDACTED]"
    assert repr(redactor) == "Redactor()"
    assert len(redactor.clean("a" * 2000)) == 1000
