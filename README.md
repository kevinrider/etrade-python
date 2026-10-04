# etrade-python

This project is currently under development and not ready for general brokerage
account access or trading.

`etrade-python` is an unofficial, async-first Python client for the E\*TRADE REST
API. It targets Python 3.11+ and is intended to provide typed request and
response models, centralized HTTP handling, OAuth session management, and broad
coverage of the officially documented E\*TRADE API.

## Project Overview

The goal is to build a modern Python library that can be used from ordinary
Python applications, CLIs, background workers, web services, workflow engines,
and notebooks.

The library is designed around:

- async networking with `httpx`
- typed models and validation with Pydantic v2
- explicit sandbox and production environments
- centralized request, retry, logging, and error handling
- conservative behavior around brokerage credentials and order mutations
- framework-independent architecture

## Current Status

Implemented:

- package skeleton using a `src` layout
- Python package metadata for the `etrade-python` distribution
- typed settings with environment variable support
- explicit sandbox and production environment handling
- async client lifecycle
- injectable async HTTP transport
- structured public exception hierarchy
- retry policy abstraction for safe read operations
- response parsing and error normalization
- sanitized operational logging boundaries
- OAuth 1.0a signing and protocol operations
- session lifecycle handling for inactivity renewal and daily expiration
- memory and keyring credential stores
- diagnostic auth, accounts, portfolio, transactions, and market data CLI
- endpoint coverage tracking
- typed Accounts service for account list and balance endpoints
- typed Portfolio and Transactions services for positions and transaction history
- typed Market service for quotes, product lookup, option expirations, and option chains
- typed Orders service for list, preview, place, change, and cancel endpoints
- local architecture and research notes
- offline tests for configuration, transport, OAuth, sessions, credential stores, CLI,
  accounts, retries, responses, logging, and client lifecycle
- Ruff, Pyright, pytest, coverage, package build, and CI configuration

Planned:

- alerts endpoints
- full endpoint-completeness review against official E*TRADE documentation

## API Coverage

Inspected 2026-10-03. OAuth, Accounts, Portfolio, Transactions, Market, and Orders
endpoints are implemented and covered by offline contract tests. Infrastructure
tests do not count as endpoint coverage. Rows marked Planned describe intended
service method/model names, not importable APIs.

Business paths are relative to `/v1` on the sandbox or production API host.
OAuth paths are relative to `https://api.etrade.com` for both environments. JSON
suffixes are format selectors and do not create separate endpoints.

| Status | Family | Official endpoint | Planned method | Planned request | Planned response | Contract tests? | Production tested? | Milestone |
|---|---|---|---|---|---|---|---|---|
| Done | OAuth | [GET /oauth/request_token](https://apisb.etrade.com/docs/api/authorization/request_token.html) | `OAuthClient.get_request_token` | - | RequestToken | Yes | Yes | 2 |
| Done | OAuth | [GET https://us.etrade.com/e/t/etws/authorize](https://apisb.etrade.com/docs/api/authorization/authorize.html) | `OAuthClient.get_authorization_url` | RequestToken | AuthorizationUrl | Yes | Yes | 2 |
| Done | OAuth | [GET /oauth/access_token](https://apisb.etrade.com/docs/api/authorization/get_access_token.html) | `OAuthClient.exchange_verifier` | RequestToken + verifier | ETradeCredentials | Yes | Yes | 2 |
| Done | OAuth | [GET /oauth/renew_access_token](https://apisb.etrade.com/docs/api/authorization/renew_access_token.html) | `OAuthClient.renew_access_token` | ETradeCredentials | RenewalResult | Yes | Yes | 2 |
| Done | OAuth | [GET /oauth/revoke_access_token](https://apisb.etrade.com/docs/api/authorization/revoke_access_token.html) | `OAuthClient.revoke_access_token` | ETradeCredentials | RevocationResult | Yes | Yes | 2 |
| Done | Accounts | [GET /accounts/list](https://apisb.etrade.com/docs/api/account/api-account-v1.html) | `accounts.list` | - | AccountListResponse | Yes | Yes | 3 |
| Done | Accounts | [GET /accounts/{accountIdKey}/balance](https://apisb.etrade.com/docs/api/account/api-balance-v1.html) | `accounts.get_balance` | AccountBalanceRequest | AccountBalanceResponse | Yes | Yes | 3 |
| Done | Portfolio | [GET /accounts/{accountIdKey}/portfolio](https://apisb.etrade.com/docs/api/account/api-portfolio-v1.html) | `portfolio.get_positions / iter_positions` | PortfolioRequest | PortfolioResponse including PositionLot | Yes | Yes | 4 |
| Done | Transactions | [GET /accounts/{accountIdKey}/transactions](https://apisb.etrade.com/docs/api/account/api-transaction-v1.html) | `transactions.list` | TransactionsRequest | TransactionsResponse | Yes | Yes | 4 |
| Done | Transactions | [GET /accounts/{accountIdKey}/transactions/{tranid}](https://apisb.etrade.com/docs/api/account/api-transaction-v1.html) | `transactions.get` | TransactionDetailsRequest | TransactionDetailsResponse | Yes | Yes | 4 |
| Done | Market | [GET /market/quote/{symbols}](https://apisb.etrade.com/docs/api/market/api-quote-v1.html) | `market.get_quote / get_quotes` | QuotesRequest | Quote / QuotesResponse | Yes | Yes | 5 |
| Done | Market | [GET /market/lookup/{search}](https://apisb.etrade.com/docs/api/market/api-market-v1.html) | `market.lookup_product` | ProductLookupRequest | ProductLookupResponse | Yes | Yes | 5 |
| Done | Market | [GET /market/optionexpiredate](https://apisb.etrade.com/docs/api/market/api-market-v1.html) | `market.get_option_expirations` | OptionExpirationsRequest | OptionExpirationsResponse | Yes | Yes | 5 |
| Done | Market | [GET /market/optionchains](https://apisb.etrade.com/docs/api/market/api-market-v1.html) | `market.get_option_chain` | OptionChainRequest | OptionChainResponse | Yes | Yes | 5 |
| Done | Orders | [GET /accounts/{accountIdKey}/orders](https://apisb.etrade.com/docs/api/order/api-order-v1.html) | `orders.list / list_all` | OrdersRequest | OrdersResponse | Yes | Yes | 6 |
| Done | Orders | [POST /accounts/{accountIdKey}/orders/preview](https://apisb.etrade.com/docs/api/order/api-order-v1.html) | `orders.preview` | PreviewOrderRequest | PreviewOrderResponse | Yes | No | 6 |
| Done | Orders | [POST /accounts/{accountIdKey}/orders/place](https://apisb.etrade.com/docs/api/order/api-order-v1.html) | `orders.place` | PlaceOrderRequest | PlaceOrderResponse | Yes | No | 6 |
| Done | Orders | [PUT /accounts/{accountIdKey}/orders/{orderId}/change/preview](https://apisb.etrade.com/docs/api/order/api-order-v1.html) | `orders.preview_change` | PreviewOrderRequest | PreviewOrderResponse | Yes | No | 6 |
| Done | Orders | [PUT /accounts/{accountIdKey}/orders/{orderId}/change/place](https://apisb.etrade.com/docs/api/order/api-order-v1.html) | `orders.place_change` | PlaceOrderRequest | PlaceOrderResponse | Yes | No | 6 |
| Done | Orders | [PUT /accounts/{accountIdKey}/orders/cancel](https://apisb.etrade.com/docs/api/order/api-order-v1.html) | `orders.cancel` | CancelOrderRequest | CancelOrderResponse | Yes | No | 6 |
| Planned | Alerts | [GET /user/alerts](https://apisb.etrade.com/docs/api/user/api-alert-v1.html) | `alerts.list` | AlertsRequest | AlertsResponse | No | No | 7 |
| Planned | Alerts | [GET /user/alerts/{id}](https://apisb.etrade.com/docs/api/user/api-alert-v1.html) | `alerts.get` | AlertDetailsRequest | Alert | No | No | 7 |
| Planned | Alerts | [DELETE /user/alerts/{alert_id_list}](https://apisb.etrade.com/docs/api/user/api-alert-v1.html) | `alerts.delete` | DeleteAlertsRequest | DeleteAlertsResponse | No | No | 7 |

## Key Technologies

- Python 3.11+
- `httpx`
- `keyring`
- Pydantic v2
- `pydantic-settings`
- `pytest`
- Ruff
- Pyright
- Typer
- uv-compatible development workflow

## Diagnostic CLI

The CLI is intended for authentication bootstrap and manual read-only diagnostics.
After authenticating with `etrade auth login`, you can manually exercise the
read-only account, portfolio, transactions, and market data endpoints:

```sh
.venv/bin/etrade accounts list
.venv/bin/etrade accounts list --json
.venv/bin/etrade accounts balance ACCOUNT_ID_KEY
.venv/bin/etrade accounts balance ACCOUNT_ID_KEY --account-type CASH --real-time-nav
.venv/bin/etrade accounts balance ACCOUNT_ID_KEY --json
.venv/bin/etrade portfolio positions ACCOUNT_ID_KEY
.venv/bin/etrade portfolio positions ACCOUNT_ID_KEY --json
.venv/bin/etrade transactions list ACCOUNT_ID_KEY
.venv/bin/etrade transactions list ACCOUNT_ID_KEY --json
.venv/bin/etrade transactions get ACCOUNT_ID_KEY TRANSACTION_ID
.venv/bin/etrade transactions get ACCOUNT_ID_KEY TRANSACTION_ID --json
.venv/bin/etrade market quote AAPL
.venv/bin/etrade market quote AAPL --json
.venv/bin/etrade market quotes AAPL MSFT
.venv/bin/etrade market lookup Apple
.venv/bin/etrade market option-expirations AAPL
.venv/bin/etrade market option-chain AAPL --expiry-year 2026 --expiry-month 10 --expiry-day 16
.venv/bin/etrade orders list ACCOUNT_ID_KEY
.venv/bin/etrade orders preview ACCOUNT_ID_KEY preview-order.json
.venv/bin/etrade orders place ACCOUNT_ID_KEY place-order.json --confirm-live-order
.venv/bin/etrade orders preview-change ACCOUNT_ID_KEY ORDER_ID preview-order.json
.venv/bin/etrade orders place-change ACCOUNT_ID_KEY ORDER_ID place-order.json --confirm-live-order
.venv/bin/etrade orders cancel ACCOUNT_ID_KEY ORDER_ID --confirm-live-order
```

The account commands display account IDs and account ID keys because they are
needed for manual API testing. Order mutation commands require
`--confirm-live-order` because they can affect real brokerage accounts in
production. CLI commands do not print OAuth tokens, token secrets, consumer
secrets, signatures, or verifier codes.

## Order Builder

The low-level order request models remain available, but common order requests
can be composed with `OrderBuilder`:

```python
from decimal import Decimal

from etrade_python import OrderBuilder

builder = (
    OrderBuilder.for_account(account_id_key)
    .client_order_id("manualtest001")
    .equity_limit("AAPL", action="BUY", quantity=1, limit_price=Decimal("1.00"))
)

preview_request = builder.build_preview_request()
place_request = builder.build_place_request(preview_ids=[123456789])
```

The builder supports equity, single-option, vertical spread, three-leg, iron
condor, and buy-write request construction. It produces the same typed
`PreviewOrderRequest` and `PlaceOrderRequest` models accepted by
`client.orders.preview(...)`, `client.orders.place(...)`, and the change-order
methods.

## Development Setup

This repository uses `uv` for Python environment management and a `Makefile` for
common development commands. Create or reset the local virtual environment with
Python 3.11 or newer:

```sh
make venv-reset
```

Install dependencies into an existing environment:

```sh
make install
```

Run the full local validation suite:

```sh
make check
```

Run individual checks during development:

```sh
make lint
make format
make format-check
make type
make test
```

Build and validate package artifacts:

```sh
make package-check
```

Some Makefile targets remove generated local files before rebuilding them:

- `make venv-reset` removes `.venv`
- `make build` recreates `dist`
- `make clean` removes build and cache artifacts

If `make` is unavailable, use the equivalent `uv` commands directly:

```sh
uv venv --python 3.12 .venv
uv sync --extra dev
uv run ruff check .
uv run ruff format --check .
uv run pyright --pythonpath .venv/bin/python
uv run pytest
uv build
uv run python -m twine check dist/*
```

## Safety and Disclaimer

This project is not affiliated with, endorsed by, or supported by Morgan Stanley
or E*TRADE. It is a software API client, not financial advice.

Production order placement is not implemented yet. Future production trading
features will affect real brokerage accounts and must be tested carefully in the
sandbox environment before live use.

## Further Reading

- [Official E*TRADE developer documentation](https://developer.etrade.com/)
- [Contributing guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
