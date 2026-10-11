# etrade-python

An unofficial, typed, async-first Python client for the E*TRADE REST API.

`etrade-python` provides typed request and response models, OAuth 1.0a session
management, and shared async networking for Python applications, CLIs, background
workers, web services, workflow engines, and notebooks. Requires Python 3.11+.

## Features

- Namespaced Accounts, Portfolio, Transactions, Market, Orders, and Alerts services.
- Async HTTPX transport shared across services, with injectable clients and transports.
- Pydantic request/response models, Decimal monetary values, and date/datetime fields.
- Explicit sandbox and production settings; sandbox is the default.
- OAuth authorization, inactivity renewal, daily expiration, and pluggable credential stores.
- Separate order preview and placement, validated requests, and an order builder.
- Pagination helpers, structured exceptions, sanitized diagnostics, and conservative retries.
- Diagnostic CLI and interactive orders demo.

Responses are JSON only. Unknown response fields are discarded rather than exposed
as an untyped metadata dictionary. Typed models support JSON serialization and schema
inspection through Pydantic.

## Installation

Install from PyPI into an activated Python 3.11+ virtual environment:

```sh
python -m pip install etrade-python
```

Alternatively, install from a source checkout:

```sh
python -m pip install .
```

The distribution name is `etrade-python`; the import package is `etrade_python`.
The installation also provides the `etrade` command.

## API Credentials and Configuration

Obtain a consumer key and consumer secret through the
[official E*TRADE getting-started guide](https://developer.etrade.com/getting-started).
Sandbox and production require separate keys. Use credentials issued for the
configured environment.

Export these variables before using the SDK or CLI:

```sh
export ETRADE_CONSUMER_KEY='your-sandbox-consumer-key'
export ETRADE_CONSUMER_SECRET='your-sandbox-consumer-secret'
export ETRADE_ENVIRONMENT=sandbox
```

`ETRADE_ENVIRONMENT` accepts `sandbox` or `production`. Sandbox is the default;
production must be selected explicitly. Optional settings are
`ETRADE_REQUEST_TIMEOUT_SECONDS` (default `30`) and
`ETRADE_INACTIVITY_BUFFER_SECONDS` (default `300`).

`ETradeClient.from_environment()` and the CLI read environment variables. They do
not automatically load `.env`. For explicit `.env` loading in an application:

```python
from etrade_python import ETradeClient, ETradeSettings

settings = ETradeSettings(_env_file=".env")
client = ETradeClient(settings)
```

Copy `.env.example` as a starting point and replace its fake values.

## Authentication

Bootstrap authentication using the CLI:

```sh
etrade auth login
etrade auth status
```

Login prints a browser authorization URL. Open it, authorize the application, and
enter the verifier at the hidden prompt. The CLI exchanges it for access credentials
and saves them in the system keyring. Use the same environment, consumer key, and
profile when accessing those credentials from an application.

Custom profiles are optional:

```sh
etrade auth login --profile personal
etrade auth status --profile personal
etrade auth renew --profile personal
etrade auth revoke --profile personal
```

Pass `profile="personal"` to `ETradeClient(settings, profile="personal")` in SDK
code. `from_environment()` uses the default profile.

E*TRADE tokens become inactive after two hours without requests and expire at
midnight US Eastern time. The session manager renews locally inactive tokens
before an API request; expired tokens require a new login. Explicit `auth renew`
contacts the broker even when the token appears active locally.
[Official token lifecycle](https://apisb.etrade.com/docs/api/authorization/renew_access_token.html).

`auth status` reports a local lifecycle estimate, not broker verification.

## Accounts and Portfolio

After logging in with the CLI, save this as a Python script and run it with the
same environment variables:

```python
import asyncio

from etrade_python import ETradeClient


async def main() -> None:
    async with ETradeClient.from_environment() as client:
        response = await client.accounts.list()
        if not response.accounts:
            print("No accounts returned.")
            return

        account = response.accounts[0]
        account_id_key = account.account_id_key
        balance = await client.accounts.get_balance(account_id_key)
        portfolio = await client.portfolio.get_positions(account_id_key)
        print(balance.model_dump_json(indent=2))
        print(portfolio.model_dump_json(indent=2))


asyncio.run(main())
```

Account operations take `account_id_key`, the broker's routing identifier returned
by account listing, rather than the numeric `account_id`. Output can contain
sensitive account information; treat it accordingly.

## Market Data and Concurrent Requests

Independent requests can run concurrently through the shared async client:

```python
import asyncio

from etrade_python import ETradeClient


async def main() -> None:
    async with ETradeClient.from_environment() as client:
        quote, chain = await asyncio.gather(
            client.market.get_quote("AAPL"),
            client.market.get_option_chain("AAPL"),
        )
        print(quote.model_dump_json(indent=2))
        print(chain.model_dump_json(indent=2))

        products = await client.market.lookup_product("Bank of America")
        print(products.model_dump_json(indent=2))


asyncio.run(main())
```

For a specific expiration, use a date returned by the broker rather than guessing:

```python
import asyncio

from etrade_python import ETradeClient, OptionChainRequest


async def main() -> None:
    async with ETradeClient.from_environment() as client:
        response = await client.market.get_option_expirations("AAPL")
        if not response.expiration_dates:
            print("No expirations returned.")
            return

        expiration = response.expiration_dates[0]
        chain = await client.market.get_option_chain(
            "AAPL",
            OptionChainRequest(
                expiry_year=expiration.year,
                expiry_month=expiration.month,
                expiry_day=expiration.day,
                chain_type="CALLPUT",
                no_of_strikes=5,
            ),
        )
        print(chain.model_dump_json(indent=2))


asyncio.run(main())
```

## Pagination

Single-page methods return typed response models. For automatic pagination, use
`portfolio.iter_positions()`, `transactions.list_all()`, and `orders.list_all()`.
These are async iterators; despite the `list_all` name, they do not eagerly return
one combined list.

```python
import asyncio

from etrade_python import ETradeClient, TransactionsRequest


async def main() -> None:
    async with ETradeClient.from_environment() as client:
        response = await client.accounts.list()
        if not response.accounts:
            return
        account_id_key = response.accounts[0].account_id_key

        async for transaction in client.transactions.list_all(
            account_id_key, TransactionsRequest(count=50)
        ):
            print(transaction.model_dump_json())


asyncio.run(main())
```

Transaction requests default to descending order. Automatic transaction pagination
removes repeated boundary transactions and requires `count >= 2`; the single-page
`transactions.list()` method permits `count=1`. Pagination helpers reject repeated
continuation values instead of looping indefinitely.

## Order Builder and Preview

The builder produces the typed requests accepted by the Orders service. This
example previews an equity limit order; it does not place it:

```python
import asyncio
from decimal import Decimal
from uuid import uuid4

from etrade_python import ETradeClient, OrderBuilder


async def main() -> None:
    async with ETradeClient.from_environment() as client:
        response = await client.accounts.list()
        if not response.accounts:
            return
        account_id_key = response.accounts[0].account_id_key

        builder = (
            OrderBuilder.for_account(account_id_key)
            .client_order_id(uuid4().hex[:20])
            .equity_limit("AAPL", action="BUY", quantity=1, limit_price=Decimal("1.00"))
        )
        preview = await client.orders.preview(account_id_key, builder.build_preview_request())
        print(preview.model_dump_json(indent=2))


asyncio.run(main())
```pypi_tmp

The limit price is illustrative, not a trading recommendation. Preview acceptance
depends on the account and broker validations.

The builder supports equity, single-option, vertical spread, three-leg, iron-condor,
and buy-write requests. Low-level request models remain available for direct use.
Preview and placement stay separate: after reviewing an actual preview response,
pass its IDs to `builder.build_place_request(preview_ids=...)` and submit that request
with `client.orders.place(account_id_key, request)`. SDK placement methods do not
provide a CLI-style confirmation prompt; the application must control submission.

Changes use `orders.preview_change()` and `orders.place_change()`; cancellation uses
`orders.cancel()`. Production placement, changes, and cancellations affect real
brokerage accounts. Order mutations are not automatically retried. If a request
fails after submission, reconcile its broker outcome before resubmitting.

## Error Handling

The library raises structured E*TRADE exceptions rather than exposing raw HTTPX
status exceptions as its primary API:

```python
import asyncio

from etrade_python import (
    AuthenticationRequired,
    AuthorizationExpired,
    ETradeApiError,
    ETradeClient,
    ETradeError,
)


async def main() -> None:
    try:
        async with ETradeClient.from_environment() as client:
            quote = await client.market.get_quote("AAPL")
            print(quote.model_dump_json(indent=2))
    except (AuthenticationRequired, AuthorizationExpired):
        print("Run etrade auth login with the configured environment and profile.")
    except ETradeApiError as error:
        print(f"Broker request failed: HTTP {error.status_code}, code {error.broker_code}")
    except ETradeError:
        print("The client could not complete the request.")


asyncio.run(main())
```

API exceptions expose `status_code`, `broker_code`, `broker_message`, and `request_id`
when available. Diagnostics redact known request secrets, but broker messages can
still contain personal information; avoid logging them wholesale. Invalid direct
Pydantic model construction raises Pydantic validation errors.

## Credential Storage

`ETradeClient` defaults to `KeyringCredentialStore`. The operating-system keyring
backend determines storage protection; there is no automatic plaintext fallback.
Credentials are isolated by environment, consumer-key SHA-256 fingerprint, and
profile.

To use process-local memory storage:

```python
from etrade_python import ETradeClient, ETradeSettings
from etrade_python.auth import MemoryCredentialStore

store = MemoryCredentialStore()
client = ETradeClient(ETradeSettings(), credential_store=store)
```

Memory storage does not load credentials saved by the CLI and is lost when the
process exits. Use `client.oauth.get_request_token()`,
`client.oauth.get_authorization_url()`, and `client.oauth.exchange_verifier()` for
application-managed authorization, then `await client.session.save(credentials)`.
Always close the client after use. Applications can implement the async
`CredentialStore` protocol for other persistence systems.

## Diagnostic CLI and Orders Demo

Use `etrade --help` or `etrade COMMAND --help` to inspect available commands.
Add `--json` to read/preview commands for typed JSON output; it is optional.

```sh
etrade accounts list
etrade accounts balance ACCOUNT_ID_KEY
etrade portfolio positions ACCOUNT_ID_KEY
etrade transactions list ACCOUNT_ID_KEY --count 50 --json
etrade transactions get ACCOUNT_ID_KEY TRANSACTION_ID
etrade market quote AAPL
etrade market quotes AAPL MSFT
etrade market lookup "Bank of America"
etrade market option-expirations AAPL
etrade market option-chain AAPL
etrade orders list ACCOUNT_ID_KEY
etrade alerts list
etrade alerts get ALERT_ID
etrade alerts delete ALERT_ID --confirm-delete
etrade orders demo
```

The orders demo begins with account selection and supports equity, single-option,
vertical spread, three-leg, iron-condor, and buy-write scenarios. It retrieves
expirations and strikes from market data and suggests prices from quotes. Expirations
appear ten per page, with `n`/`p` navigation; the initial page shows the monthly
default when one is available. Prices and broker responses still require review.

The demo walks through preview, optional placement, change, and cancellation with
explicit confirmations. File-based order commands are also available:

```sh
etrade orders preview ACCOUNT_ID_KEY preview-order.json
etrade orders place ACCOUNT_ID_KEY place-order.json --confirm-live-order
etrade orders preview-change ACCOUNT_ID_KEY ORDER_ID preview-order.json
etrade orders place-change ACCOUNT_ID_KEY ORDER_ID place-order.json --confirm-live-order
etrade orders cancel ACCOUNT_ID_KEY ORDER_ID --confirm-live-order
```

Order JSON files use the broker request envelope emitted by the request models.
Account commands print routing identifiers for manual testing; protect their output.
Login intentionally prints the authorization URL needed for the browser flow.
Order mutation commands require `--confirm-live-order`, and alert deletion requires
`--confirm-delete`.

## Development

Use uv and the Makefile from the repository root:

```sh
make install
make check
make package-check
```

`make install` synchronizes the environment and development dependencies.
`make check` runs lint, formatting checks, type checking, and offline tests.
`make package-check` builds the wheel/source distribution and validates metadata.

Individual targets include `make lint`, `make format`, `make format-check`,
`make type`, and `make test`. `make venv-reset` deletes `.venv` and recreates it
with Python 3.12; the library itself supports Python 3.11+. `make build` recreates
`dist`, and `make clean` removes generated build and cache artifacts.

If make is unavailable:

```sh
uv sync --extra dev
uv run ruff check .
uv run ruff format --check .
uv run pyright --pythonpath .venv/bin/python
uv run pytest
uv build
uv run python -m twine check dist/*
```

CI checks Python 3.11–3.14, enforces at least 90% combined statement/branch coverage,
and verifies wheel installation outside the checkout. Push and pull-request CI
does not publish. A separate release workflow publishes stable GitHub releases
using PyPI Trusted Publishing. See
[CONTRIBUTING.md](CONTRIBUTING.md) for contribution and package verification instructions.

## API Coverage

The documented endpoint families below are implemented and covered by offline
contract tests.

Endpoint paths are relative to `/v1` on the sandbox or production API host.
OAuth paths are relative to `https://api.etrade.com` for both environments. JSON
suffixes select response format and do not create separate endpoints.

| Family | Official endpoint | Service method | Request | Response |
| --- | --- | --- | --- | --- |
| OAuth | [GET /oauth/request_token](https://apisb.etrade.com/docs/api/authorization/request_token.html) | `OAuthClient.get_request_token` | - | RequestToken |
| OAuth | [GET https://us.etrade.com/e/t/etws/authorize](https://apisb.etrade.com/docs/api/authorization/authorize.html) | `OAuthClient.get_authorization_url` | RequestToken | AuthorizationUrl |
| OAuth | [GET /oauth/access_token](https://apisb.etrade.com/docs/api/authorization/get_access_token.html) | `OAuthClient.exchange_verifier` | RequestToken + verifier | ETradeCredentials |
| OAuth | [GET /oauth/renew_access_token](https://apisb.etrade.com/docs/api/authorization/renew_access_token.html) | `OAuthClient.renew_access_token` | ETradeCredentials | RenewalResult |
| OAuth | [GET /oauth/revoke_access_token](https://apisb.etrade.com/docs/api/authorization/revoke_access_token.html) | `OAuthClient.revoke_access_token` | ETradeCredentials | RevocationResult |
| Accounts | [GET /accounts/list](https://apisb.etrade.com/docs/api/account/api-account-v1.html) | `accounts.list` | - | AccountListResponse |
| Accounts | [GET /accounts/{accountIdKey}/balance](https://apisb.etrade.com/docs/api/account/api-balance-v1.html) | `accounts.get_balance` | AccountBalanceRequest | AccountBalanceResponse |
| Portfolio | [GET /accounts/{accountIdKey}/portfolio](https://apisb.etrade.com/docs/api/account/api-portfolio-v1.html) | `portfolio.get_positions / iter_positions` | PortfolioRequest | PortfolioResponse including PositionLot |
| Transactions | [GET /accounts/{accountIdKey}/transactions](https://apisb.etrade.com/docs/api/account/api-transaction-v1.html) | `transactions.list` | TransactionsRequest | TransactionsResponse |
| Transactions | [GET /accounts/{accountIdKey}/transactions/{tranid}](https://apisb.etrade.com/docs/api/account/api-transaction-v1.html) | `transactions.get` | TransactionDetailsRequest | TransactionDetailsResponse |
| Market | [GET /market/quote/{symbols}](https://apisb.etrade.com/docs/api/market/api-quote-v1.html) | `market.get_quote / get_quotes` | QuotesRequest | Quote / QuotesResponse |
| Market | [GET /market/lookup/{search}](https://apisb.etrade.com/docs/api/market/api-market-v1.html) | `market.lookup_product` | ProductLookupRequest | ProductLookupResponse |
| Market | [GET /market/optionexpiredate](https://apisb.etrade.com/docs/api/market/api-market-v1.html) | `market.get_option_expirations` | OptionExpirationsRequest | OptionExpirationsResponse |
| Market | [GET /market/optionchains](https://apisb.etrade.com/docs/api/market/api-market-v1.html) | `market.get_option_chain` | OptionChainRequest | OptionChainResponse |
| Orders | [GET /accounts/{accountIdKey}/orders](https://apisb.etrade.com/docs/api/order/api-order-v1.html) | `orders.list / list_all` | OrdersRequest | OrdersResponse |
| Orders | [POST /accounts/{accountIdKey}/orders/preview](https://apisb.etrade.com/docs/api/order/api-order-v1.html) | `orders.preview` | PreviewOrderRequest | PreviewOrderResponse |
| Orders | [POST /accounts/{accountIdKey}/orders/place](https://apisb.etrade.com/docs/api/order/api-order-v1.html) | `orders.place` | PlaceOrderRequest | PlaceOrderResponse |
| Orders | [PUT /accounts/{accountIdKey}/orders/{orderId}/change/preview](https://apisb.etrade.com/docs/api/order/api-order-v1.html) | `orders.preview_change` | PreviewOrderRequest | PreviewOrderResponse |
| Orders | [PUT /accounts/{accountIdKey}/orders/{orderId}/change/place](https://apisb.etrade.com/docs/api/order/api-order-v1.html) | `orders.place_change` | PlaceOrderRequest | PlaceOrderResponse |
| Orders | [PUT /accounts/{accountIdKey}/orders/cancel](https://apisb.etrade.com/docs/api/order/api-order-v1.html) | `orders.cancel` | CancelOrderRequest | CancelOrderResponse |
| Alerts | [GET /user/alerts](https://apisb.etrade.com/docs/api/user/api-alert-v1.html) | `alerts.list` | AlertsRequest | AlertsResponse |
| Alerts | [GET /user/alerts/{id}](https://apisb.etrade.com/docs/api/user/api-alert-v1.html) | `alerts.get` | AlertDetailsRequest | AlertDetailsResponse |
| Alerts | [DELETE /user/alerts/{alert_id_list}](https://apisb.etrade.com/docs/api/user/api-alert-v1.html) | `alerts.delete` | alert ID list | DeleteAlertsResponse |

## Safety and License

This project is not affiliated with, endorsed by, or supported by Morgan Stanley
or E*TRADE. It is a software API client, not financial advice.

Production trading methods affect real brokerage accounts. Start in sandbox,
review request details and broker confirmations, and keep secrets and sensitive
account output out of source control and public logs. Read the
[security policy](SECURITY.md) for storage, logging, and mutation considerations.

Licensed under [Apache-2.0](LICENSE).

## Further Reading

- [Official E*TRADE developer documentation](https://developer.etrade.com/)
- [Changelog](CHANGELOG.md)
- [Contributing guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
