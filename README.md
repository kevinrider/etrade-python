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
- diagnostic auth CLI
- endpoint coverage tracking
- local architecture and research notes
- offline tests for configuration, transport, OAuth, sessions, credential stores, CLI,
  retries, responses, logging, and client lifecycle
- Ruff, Pyright, pytest, coverage, package build, and CI configuration

Planned:

- accounts endpoints
- portfolio endpoints
- transactions endpoints
- market data endpoints
- order preview, placement, modification, and cancellation endpoints
- alerts endpoints
- full endpoint-completeness review against official E*TRADE documentation

## API Coverage

Inspected 2026-09-26. OAuth endpoints are implemented and covered by offline
contract tests. No business API endpoints are implemented yet. Infrastructure
tests do not count as endpoint coverage. Business service method/model names
below are planned, not importable APIs.

Business paths are relative to `/v1` on the sandbox or production API host.
OAuth paths are relative to `https://api.etrade.com` for both environments. JSON
suffixes are format selectors and do not create separate endpoints.

| Family | Official endpoint | Planned method | Planned request | Planned response | Implemented? | Contract tests? | Sandbox tested? | Production tested? | Milestone |
|---|---|---|---|---|---|---|---|---|---|
| OAuth | [GET /oauth/request_token](https://apisb.etrade.com/docs/api/authorization/request_token.html) | `OAuthClient.get_request_token` | - | RequestToken | Yes | Yes | No | No | 2 |
| OAuth | [GET https://us.etrade.com/e/t/etws/authorize](https://apisb.etrade.com/docs/api/authorization/authorize.html) | `OAuthClient.get_authorization_url` | RequestToken | AuthorizationUrl | Yes | Yes | No | No | 2 |
| OAuth | [GET /oauth/access_token](https://apisb.etrade.com/docs/api/authorization/get_access_token.html) | `OAuthClient.exchange_verifier` | RequestToken + verifier | ETradeCredentials | Yes | Yes | No | No | 2 |
| OAuth | [GET /oauth/renew_access_token](https://apisb.etrade.com/docs/api/authorization/renew_access_token.html) | `OAuthClient.renew_access_token` | ETradeCredentials | RenewalResult | Yes | Yes | No | No | 2 |
| OAuth | [GET /oauth/revoke_access_token](https://apisb.etrade.com/docs/api/authorization/revoke_access_token.html) | `OAuthClient.revoke_access_token` | ETradeCredentials | RevocationResult | Yes | Yes | No | No | 2 |
| Accounts | [GET /accounts/list](https://apisb.etrade.com/docs/api/account/api-account-v1.html) | `accounts.list` | - | list[Account] | No | No | No | No | 3 |
| Accounts | [GET /accounts/{accountIdKey}/balance](https://apisb.etrade.com/docs/api/account/api-balance-v1.html) | `accounts.get_balance` | BalanceRequest | AccountBalance | No | No | No | No | 3 |
| Portfolio | [GET /accounts/{accountIdKey}/portfolio](https://apisb.etrade.com/docs/api/account/api-portfolio-v1.html) | `portfolio.get_positions` | PositionsRequest | PositionsPage | No | No | No | No | 4 |
| Portfolio* | [GET /accounts/{accountIdKey}/portfolio/{positionId}](https://apisb.etrade.com/docs/api/account/api-portfolio-v1.html) | `portfolio.get_position_lots` | PositionLotsRequest | PositionLots | No | No | No | No | 4 |
| Transactions | [GET /accounts/{accountIdKey}/transactions](https://apisb.etrade.com/docs/api/account/api-transaction-v1.html) | `transactions.list` | TransactionsRequest | TransactionsPage | No | No | No | No | 4 |
| Transactions | [GET /accounts/{accountIdKey}/transactions/{tranid}](https://apisb.etrade.com/docs/api/account/api-transaction-v1.html) | `transactions.get` | TransactionDetailsRequest | Transaction | No | No | No | No | 4 |
| Market | [GET /market/quote/{symbols}](https://apisb.etrade.com/docs/api/market/api-quote-v1.html) | `market.get_quote / get_quotes` | QuotesRequest | Quote / QuotesResponse | No | No | No | No | 5 |
| Market | [GET /market/lookup/{search}](https://apisb.etrade.com/docs/api/market/api-market-v1.html) | `market.lookup_product` | ProductLookupRequest | ProductsResponse | No | No | No | No | 5 |
| Market | [GET /market/optionexpiredate](https://apisb.etrade.com/docs/api/market/api-market-v1.html) | `market.get_option_expirations` | OptionExpirationsRequest | OptionExpirationsResponse | No | No | No | No | 5 |
| Market | [GET /market/optionchains](https://apisb.etrade.com/docs/api/market/api-market-v1.html) | `market.get_option_chain` | OptionChainRequest | OptionChain | No | No | No | No | 5 |
| Orders | [GET /accounts/{accountIdKey}/orders](https://apisb.etrade.com/docs/api/order/api-order-v1.html) | `orders.list` | OrdersRequest | OrdersPage | No | No | No | No | 6 |
| Orders* | [GET /accounts/{accountIdKey}/orders/{orderId}](https://apisb.etrade.com/docs/api/order/api-order-v1.html) | `orders.get` | OrderDetailsRequest | Order | No | No | No | No | 6 |
| Orders | [POST /accounts/{accountIdKey}/orders/preview](https://apisb.etrade.com/docs/api/order/api-order-v1.html) | `orders.preview` | OrderPreviewRequest | OrderPreview | No | No | No | No | 6 |
| Orders | [POST /accounts/{accountIdKey}/orders/place](https://apisb.etrade.com/docs/api/order/api-order-v1.html) | `orders.place` | OrderPlacementRequest | OrderExecution | No | No | No | No | 6 |
| Orders | [PUT /accounts/{accountIdKey}/orders/{orderId}/change/preview](https://apisb.etrade.com/docs/api/order/api-order-v1.html) | `orders.preview_change` | OrderChangePreviewRequest | OrderPreview | No | No | No | No | 6 |
| Orders | [PUT /accounts/{accountIdKey}/orders/{orderId}/change/place](https://apisb.etrade.com/docs/api/order/api-order-v1.html) | `orders.modify` | OrderModificationRequest | OrderExecution | No | No | No | No | 6 |
| Orders | [PUT /accounts/{accountIdKey}/orders/cancel](https://apisb.etrade.com/docs/api/order/api-order-v1.html) | `orders.cancel` | OrderCancellationRequest | OrderCancellation | No | No | No | No | 6 |
| Alerts | [GET /user/alerts](https://apisb.etrade.com/docs/api/user/api-alert-v1.html) | `alerts.list` | AlertsRequest | AlertsResponse | No | No | No | No | 7 |
| Alerts | [GET /user/alerts/{id}](https://apisb.etrade.com/docs/api/user/api-alert-v1.html) | `alerts.get` | AlertDetailsRequest | Alert | No | No | No | No | 7 |
| Alerts | [DELETE /user/alerts/{alert_id_list}](https://apisb.etrade.com/docs/api/user/api-alert-v1.html) | `alerts.delete` | DeleteAlertsRequest | DeleteAlertsResponse | No | No | No | No | 7 |

*Partially documented in official response examples, without a standalone
complete endpoint specification. Confirm the contract before implementing.*

Milestone 8 will recheck the official documentation and fill gaps. Sandbox and
production evidence must include date and scenario when actually collected;
offline fixtures alone never change those columns.

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

## Development Setup

Create a virtual environment with Python 3.11 or newer:

```sh
uv python install 3.12
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e '.[dev]'
```

Run the main checks:

```sh
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/pyright --pythonpath .venv/bin/python
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
