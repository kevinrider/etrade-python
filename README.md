# etrade-python

An unofficial, async-first, typed Python client for the E*TRADE REST API.
Python 3.11+. Apache-2.0. Independent of MCP and any application framework.

**Development status:** foundation only (`0.1.0.dev0`). Settings, HTTP transport,
errors, retries, and lifecycle management are implemented. OAuth, credential
stores, API services, and the diagnostic CLI are not implemented. This is not
ready to access brokerage accounts or place orders. See [coverage](docs/api-coverage.md).

## Development installation

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

The intended PyPI name is `etrade-python` and import name is `etrade_python`.
This repository does not claim a published release or ownership of that PyPI name.

## Configuration and lifecycle

```python
from etrade_python import ETradeClient, ETradeSettings

# Environment: ETRADE_CONSUMER_KEY and ETRADE_CONSUMER_SECRET are required.
# ETRADE_ENVIRONMENT defaults to sandbox; production must be explicit.
settings = ETradeSettings()
# Optional local dotenv loading: ETradeSettings(_env_file=".env")


async def main() -> None:
    async with ETradeClient(settings) as client:
        # Future services will share this client's transport and session.
        pass
```

`ETradeClient.from_environment()` also loads settings, without automatically
reading dotenv files. Constructor arguments override environment values;
environment values override explicitly loaded dotenv values. Secrets are masked
in serialization and excluded from settings repr. Invalid constructor settings
raise `ETradeValidationError` without echoing input values.

Timeout defaults to 30 seconds (`ETRADE_REQUEST_TIMEOUT_SECONDS`).
`ETRADE_INACTIVITY_BUFFER_SECONDS` defaults to 300; session handling is deferred.

Obtain separate sandbox and production consumer keys through the
[official getting-started instructions](https://developer.etrade.com/getting-started).
Both environments use the same OAuth server. Sandbox returns canned data that
may not match requested symbols; it is not a market simulator. See the
[official developer guide](https://developer.etrade.com/getting-started/developer-guides).

## Transport testing

The transport is a low-level extension point. Business methods and their typed
models will be the ordinary application interface. Until OAuth is implemented,
a request without an injected authenticator raises `AuthenticationRequired`.
Use fake authentication only with a mock HTTP transport:

```python
import httpx
from etrade_python import ETradeSettings
from etrade_python.transport import ApiTransport


class FakeAuthenticator:
    async def authenticate(self, request: httpx.Request) -> None:
        request.headers["Authorization"] = 'OAuth oauth_token="fake-token"'


async def test_request() -> None:
    settings = ETradeSettings(consumer_key="fake-key", consumer_secret="fake-secret")
    mock = httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))
    async with ApiTransport(
        settings, authenticator=FakeAuthenticator(), http_transport=mock
    ) as api:
        response = await api.request("GET", "/v1/example.json", operation="example.read")
        assert response.data == {"ok": True}
```

An injected `http_client=httpx.AsyncClient(...)` stays caller-owned. Supplying
`http_transport=...` creates an internally owned client which is closed on exit.
Do not provide both. Internal clients disable environment proxies (`trust_env=False`);
applications needing a proxy can inject a configured client. Independent requests
can run with `asyncio.gather`; do not close a client while requests are in flight.

No retries occur by default. `RetrySafety.SAFE_READ` opts a GET/HEAD operation
into bounded retries for selected transient failures. Never classify a mutation,
OAuth lifecycle call, or unverified operation as a safe read. Each attempt is
authenticated afresh. Decimal request values become strings; fractional JSON
response values decode directly to Decimal. HTTP 204 returns `data=None`.

## Errors and security

Catch `ETradeError` for library failures. HTTP failures expose sanitized
`status_code`, `broker_code`, `broker_message`, and `request_id` attributes through
`ETradeApiError`; transport failures raise `ETradeTransportError`. Timeouts during
mutations can leave the broker outcome unknown and must not trigger blind resubmission.

See [SECURITY.md](SECURITY.md). Avoid credential-bearing hooks and custom wire logging on injected clients.
Automatic HTTPX/httpcore logs are suppressed only during SDK exchanges, using
task-local context; unrelated application requests retain their logging.
The library's own logs contain operation labels,
environment, status, latency, and attempt numbers, not URLs or payloads.

Future order-placement methods will affect real brokerage accounts in production;
preview and placement will remain separate operations. No production trading tests
will run in routine CI. Keyring will be the default persistent local credential store
when OAuth is implemented; no credentials are persisted in this version.

## Checks and roadmap

See [CONTRIBUTING.md](CONTRIBUTING.md) for checks and package verification,
[architecture](docs/architecture.md) for boundaries, and
[research notes](docs/research-notes.md) for source review and unresolved questions.
Next: OAuth/session lifecycle, stores, and authentication CLI, followed by accounts.

This project is not affiliated with, endorsed by, or supported by Morgan Stanley
or E*TRADE. It is a software API client, not financial advice.
