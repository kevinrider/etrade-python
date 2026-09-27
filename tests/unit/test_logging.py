import asyncio
import logging

import pytest

from etrade_python.transport.logging import private_http_exchange


async def test_http_logging_is_scoped_to_task(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    entered, release = asyncio.Event(), asyncio.Event()

    async def sdk_exchange() -> None:
        with private_http_exchange():
            entered.set()
            logging.getLogger("httpx").info("fake-sensitive-url")
            logging.getLogger("httpcore.http11").debug("fake-sensitive-headers")
            await release.wait()

    task = asyncio.create_task(sdk_exchange())
    await asyncio.wait_for(entered.wait(), timeout=2)
    logging.getLogger("httpx").info("unrelated application request")
    release.set()
    await task
    logging.getLogger("httpx").info("after SDK request")
    assert "fake-sensitive" not in caplog.text
    assert "unrelated application request" in caplog.text
    assert "after SDK request" in caplog.text


def test_http_logging_restored_after_exception(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    with pytest.raises(ValueError), private_http_exchange():
        raise ValueError("example")
    logging.getLogger("httpx").info("after error")
    assert "after error" in caplog.text
