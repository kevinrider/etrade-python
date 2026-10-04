"""Diagnostic CLI for authentication bootstrap and read-only API checks."""

import asyncio
import json
from collections.abc import Coroutine
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Any, TypeVar, cast
from uuid import uuid4

import typer
from pydantic import BaseModel

from etrade_python import (
    Account,
    AccountBalanceRequest,
    AccountBalanceResponse,
    AccountListResponse,
    CancelOrderResponse,
    OptionChainRequest,
    OptionChainResponse,
    OptionContract,
    OptionExpiration,
    OptionExpirationsRequest,
    OptionExpirationsResponse,
    OrderBuilder,
    OrdersRequest,
    OrdersResponse,
    PlaceOrderRequest,
    PlaceOrderResponse,
    PortfolioRequest,
    PortfolioResponse,
    PreviewOrderRequest,
    PreviewOrderResponse,
    ProductLookupResponse,
    Quote,
    QuotesRequest,
    QuotesResponse,
    TransactionDetailsRequest,
    TransactionDetailsResponse,
    TransactionsRequest,
    TransactionsResponse,
    __version__,
)
from etrade_python.auth import TokenStatus
from etrade_python.client import ETradeClient
from etrade_python.config import ETradeSettings
from etrade_python.exceptions import ETradeError

TModel = TypeVar("TModel", bound=BaseModel)
TChoice = TypeVar("TChoice")

app = typer.Typer(no_args_is_help=True, invoke_without_command=True)
auth_app = typer.Typer(no_args_is_help=True)
accounts_app = typer.Typer(no_args_is_help=True)
portfolio_app = typer.Typer(no_args_is_help=True)
transactions_app = typer.Typer(no_args_is_help=True)
market_app = typer.Typer(no_args_is_help=True)
orders_app = typer.Typer(no_args_is_help=True)
app.add_typer(auth_app, name="auth")
app.add_typer(accounts_app, name="accounts")
app.add_typer(portfolio_app, name="portfolio")
app.add_typer(transactions_app, name="transactions")
app.add_typer(market_app, name="market")
app.add_typer(orders_app, name="orders")


def _run(coro: Coroutine[Any, Any, object]) -> object:
    return asyncio.run(coro)


def _settings() -> ETradeSettings:
    return ETradeSettings()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", help="Show package version and exit."),
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@auth_app.command("login")
def login(profile: str = typer.Option("default", "--profile", "-p")) -> None:
    """Start OAuth authorization and save the resulting access token."""

    async def command() -> None:
        async with ETradeClient(_settings(), profile=profile) as client:
            request_token = await client.oauth.get_request_token()
            authorization = client.oauth.get_authorization_url(request_token)
            typer.echo("Open this URL in a browser and authorize the application:")
            typer.echo(authorization.url)
            verifier = typer.prompt("OAuth verifier", hide_input=True)
            credentials = await client.oauth.exchange_verifier(request_token, verifier)
            await client.session.save(credentials)
            typer.echo(f"Credentials saved for profile '{profile}'.")

    _handle(command())


@auth_app.command("status")
def status(profile: str = typer.Option("default", "--profile", "-p")) -> None:
    """Show credential lifecycle status without exposing tokens."""

    async def command() -> None:
        async with ETradeClient(_settings(), profile=profile) as client:
            credentials = await client.session.load()
            token_status = client.session.status(credentials)
            if token_status is TokenStatus.MISSING:
                typer.echo(f"No credentials stored for profile '{profile}'.")
            else:
                typer.echo(f"Credentials for profile '{profile}' are {token_status.value}.")

    _handle(command())


@auth_app.command("renew")
def renew(profile: str = typer.Option("default", "--profile", "-p")) -> None:
    """Renew inactive credentials when they are still same-day valid."""

    async def command() -> None:
        async with ETradeClient(_settings(), profile=profile) as client:
            await client.session.ensure_active()
            typer.echo(f"Credentials for profile '{profile}' are active.")

    _handle(command())


@auth_app.command("revoke")
def revoke(profile: str = typer.Option("default", "--profile", "-p")) -> None:
    """Revoke and delete stored credentials."""

    async def command() -> None:
        async with ETradeClient(_settings(), profile=profile) as client:
            credentials = await client.session.load()
            if credentials is not None:
                await client.oauth.revoke_access_token(credentials)
            await client.session.delete()
            typer.echo(f"Credentials removed for profile '{profile}'.")

    _handle(command())


@accounts_app.command("list")
def list_accounts(
    profile: str = typer.Option("default", "--profile", "-p"),
    json_output: bool = typer.Option(False, "--json", help="Print the full response as JSON."),
) -> None:
    """List brokerage accounts for the current profile."""

    async def command() -> None:
        async with ETradeClient(_settings(), profile=profile) as client:
            response = await client.accounts.list()
            if json_output:
                _echo_json(response)
                return
            _echo_account_list(response)

    _handle(command())


@accounts_app.command("balance")
def account_balance(
    account_id_key: str = typer.Argument(..., help="E*TRADE accountIdKey from accounts list."),
    profile: str = typer.Option("default", "--profile", "-p"),
    account_type: str | None = typer.Option(None, "--account-type"),
    inst_type: str = typer.Option("BROKERAGE", "--inst-type"),
    real_time_nav: bool = typer.Option(False, "--real-time-nav"),
    json_output: bool = typer.Option(False, "--json", help="Print the full response as JSON."),
) -> None:
    """Show account balance details for an accountIdKey."""

    async def command() -> None:
        request = AccountBalanceRequest(
            account_type=account_type,
            inst_type=inst_type,
            real_time_nav=real_time_nav,
        )
        async with ETradeClient(_settings(), profile=profile) as client:
            response = await client.accounts.get_balance(account_id_key, request)
            if json_output:
                _echo_json(response)
                return
            _echo_account_balance(response)

    _handle(command())


@portfolio_app.command("positions")
def portfolio_positions(
    account_id_key: str = typer.Argument(..., help="E*TRADE accountIdKey from accounts list."),
    profile: str = typer.Option("default", "--profile", "-p"),
    count: int | None = typer.Option(None, "--count"),
    page_number: int | None = typer.Option(None, "--page-number"),
    view: str | None = typer.Option(None, "--view"),
    lots_required: bool | None = typer.Option(None, "--lots-required/--no-lots-required"),
    totals_required: bool | None = typer.Option(None, "--totals-required/--no-totals-required"),
    json_output: bool = typer.Option(False, "--json", help="Print the full response as JSON."),
) -> None:
    """Show portfolio positions for an accountIdKey."""

    async def command() -> None:
        request = PortfolioRequest(
            count=count,
            page_number=page_number,
            view=view,
            lots_required=lots_required,
            totals_required=totals_required,
        )
        async with ETradeClient(_settings(), profile=profile) as client:
            response = await client.portfolio.get_positions(account_id_key, request)
            if json_output:
                _echo_json(response)
                return
            _echo_portfolio(response)

    _handle(command())


@transactions_app.command("list")
def list_transactions(
    account_id_key: str = typer.Argument(..., help="E*TRADE accountIdKey from accounts list."),
    profile: str = typer.Option("default", "--profile", "-p"),
    marker: str | None = typer.Option(None, "--marker"),
    count: int | None = typer.Option(None, "--count"),
    start_date: str | None = typer.Option(None, "--start-date"),
    end_date: str | None = typer.Option(None, "--end-date"),
    sort_order: str | None = typer.Option(None, "--sort-order"),
    json_output: bool = typer.Option(False, "--json", help="Print the full response as JSON."),
) -> None:
    """List transactions for an accountIdKey."""

    async def command() -> None:
        request = TransactionsRequest(
            marker=marker,
            count=count,
            start_date=start_date,
            end_date=end_date,
            sort_order=sort_order,
        )
        async with ETradeClient(_settings(), profile=profile) as client:
            response = await client.transactions.list(account_id_key, request)
            if json_output:
                _echo_json(response)
                return
            _echo_transactions(response)

    _handle(command())


@transactions_app.command("get")
def get_transaction(
    account_id_key: str = typer.Argument(..., help="E*TRADE accountIdKey from accounts list."),
    transaction_id: str = typer.Argument(..., help="Transaction ID from transactions list."),
    profile: str = typer.Option("default", "--profile", "-p"),
    store_id: str | None = typer.Option(None, "--store-id"),
    json_output: bool = typer.Option(False, "--json", help="Print the full response as JSON."),
) -> None:
    """Show transaction details for a transaction ID."""

    async def command() -> None:
        request = TransactionDetailsRequest(store_id=store_id)
        async with ETradeClient(_settings(), profile=profile) as client:
            response = await client.transactions.get(account_id_key, transaction_id, request)
            if json_output:
                _echo_json(response)
                return
            _echo_transaction_details(response)

    _handle(command())


@orders_app.command("list")
def list_orders(
    account_id_key: str = typer.Argument(..., help="E*TRADE accountIdKey from accounts list."),
    profile: str = typer.Option("default", "--profile", "-p"),
    marker: str | None = typer.Option(None, "--marker"),
    count: int | None = typer.Option(None, "--count"),
    status: str | None = typer.Option(None, "--status"),
    from_date: str | None = typer.Option(None, "--from-date"),
    to_date: str | None = typer.Option(None, "--to-date"),
    symbol: str | None = typer.Option(None, "--symbol"),
    security_type: str | None = typer.Option(None, "--security-type"),
    transaction_type: str | None = typer.Option(None, "--transaction-type"),
    market_session: str | None = typer.Option(None, "--market-session"),
    json_output: bool = typer.Option(False, "--json", help="Print the full response as JSON."),
) -> None:
    """List orders for an accountIdKey."""

    async def command() -> None:
        request = OrdersRequest(
            marker=marker,
            count=count,
            status=status,
            fromDate=from_date,
            toDate=to_date,
            symbol=symbol,
            securityType=security_type,
            transactionType=transaction_type,
            marketSession=market_session,
        )
        async with ETradeClient(_settings(), profile=profile) as client:
            response = await client.orders.list(account_id_key, request)
            if json_output:
                _echo_json(response)
                return
            _echo_orders(response)

    _handle(command())


@orders_app.command("preview")
def preview_order(
    account_id_key: Annotated[str, typer.Argument(help="E*TRADE accountIdKey from accounts list.")],
    request_json: Annotated[Path, typer.Argument(help="JSON file containing PreviewOrderRequest.")],
    profile: str = typer.Option("default", "--profile", "-p"),
    json_output: bool = typer.Option(False, "--json", help="Print the full response as JSON."),
) -> None:
    """Preview an order request from a JSON file."""

    async def command() -> None:
        request = _load_model_file(request_json, PreviewOrderRequest, "PreviewOrderRequest")
        async with ETradeClient(_settings(), profile=profile) as client:
            response = await client.orders.preview(account_id_key, request)
            if json_output:
                _echo_json(response)
                return
            _echo_preview_order(response)

    _handle(command())


@orders_app.command("place")
def place_order(
    account_id_key: Annotated[str, typer.Argument(help="E*TRADE accountIdKey from accounts list.")],
    request_json: Annotated[Path, typer.Argument(help="JSON file containing PlaceOrderRequest.")],
    profile: str = typer.Option("default", "--profile", "-p"),
    confirm_live_order: bool = typer.Option(False, "--confirm-live-order"),
    json_output: bool = typer.Option(False, "--json", help="Print the full response as JSON."),
) -> None:
    """Place a previously previewed order request from a JSON file."""

    _require_live_order_confirmation(confirm_live_order)

    async def command() -> None:
        request = _load_model_file(request_json, PlaceOrderRequest, "PlaceOrderRequest")
        async with ETradeClient(_settings(), profile=profile) as client:
            response = await client.orders.place(account_id_key, request)
            if json_output:
                _echo_json(response)
                return
            _echo_place_order(response)

    _handle(command())


@orders_app.command("preview-change")
def preview_change_order(
    account_id_key: Annotated[str, typer.Argument(help="E*TRADE accountIdKey from accounts list.")],
    order_id: Annotated[int, typer.Argument(help="Order ID to change.")],
    request_json: Annotated[Path, typer.Argument(help="JSON file containing PreviewOrderRequest.")],
    profile: str = typer.Option("default", "--profile", "-p"),
    json_output: bool = typer.Option(False, "--json", help="Print the full response as JSON."),
) -> None:
    """Preview a changed order request from a JSON file."""

    async def command() -> None:
        request = _load_model_file(request_json, PreviewOrderRequest, "PreviewOrderRequest")
        async with ETradeClient(_settings(), profile=profile) as client:
            response = await client.orders.preview_change(account_id_key, order_id, request)
            if json_output:
                _echo_json(response)
                return
            _echo_preview_order(response)

    _handle(command())


@orders_app.command("place-change")
def place_change_order(
    account_id_key: Annotated[str, typer.Argument(help="E*TRADE accountIdKey from accounts list.")],
    order_id: Annotated[int, typer.Argument(help="Order ID to change.")],
    request_json: Annotated[Path, typer.Argument(help="JSON file containing PlaceOrderRequest.")],
    profile: str = typer.Option("default", "--profile", "-p"),
    confirm_live_order: bool = typer.Option(False, "--confirm-live-order"),
    json_output: bool = typer.Option(False, "--json", help="Print the full response as JSON."),
) -> None:
    """Place a changed order request from a JSON file."""

    _require_live_order_confirmation(confirm_live_order)

    async def command() -> None:
        request = _load_model_file(request_json, PlaceOrderRequest, "PlaceOrderRequest")
        async with ETradeClient(_settings(), profile=profile) as client:
            response = await client.orders.place_change(account_id_key, order_id, request)
            if json_output:
                _echo_json(response)
                return
            _echo_place_order(response)

    _handle(command())


@orders_app.command("cancel")
def cancel_order(
    account_id_key: str = typer.Argument(..., help="E*TRADE accountIdKey from accounts list."),
    order_id: int = typer.Argument(..., help="Order ID to cancel."),
    profile: str = typer.Option("default", "--profile", "-p"),
    confirm_live_order: bool = typer.Option(False, "--confirm-live-order"),
    json_output: bool = typer.Option(False, "--json", help="Print the full response as JSON."),
) -> None:
    """Cancel an order."""

    _require_live_order_confirmation(confirm_live_order)

    async def command() -> None:
        async with ETradeClient(_settings(), profile=profile) as client:
            response = await client.orders.cancel(account_id_key, order_id)
            if json_output:
                _echo_json(response)
                return
            _echo_cancel_order(response)

    _handle(command())


@orders_app.command("demo")
def orders_demo(
    profile: str = typer.Option("default", "--profile", "-p"),
) -> None:
    """Run an interactive order preview/place/change/cancel demo."""

    async def command() -> None:
        settings = _settings()
        async with ETradeClient(settings, profile=profile) as client:
            accounts = await client.accounts.list()
            account = _prompt_account(accounts)
            account_id_key = account.account_id_key
            typer.echo(f"Profile: {profile}")
            typer.echo(f"Environment: {settings.environment.value}")
            typer.echo(f"Selected accountIdKey: {account_id_key}")

            scenario = _prompt_order_scenario()
            builder = await _build_demo_order(client, account_id_key, scenario)
            preview_request = builder.build_preview_request()
            typer.echo("Generated preview request:")
            _echo_json(preview_request.request_body())

            preview = await client.orders.preview(account_id_key, preview_request)
            typer.echo("Preview response:")
            _echo_preview_order(preview)
            preview_ids = _preview_ids(preview)
            if not preview_ids:
                typer.echo("No preview IDs were returned; skipping placement.")
                return

            if not _confirm_live_action("place this order", settings):
                typer.echo("Order placement skipped.")
                return

            place_request = builder.build_place_request(preview_ids)
            place = await client.orders.place(account_id_key, place_request)
            typer.echo("Place response:")
            _echo_place_order(place)
            order_id = _first_order_id(place)
            if order_id is None:
                typer.echo("No order ID was returned; skipping change and cancel steps.")
                return

            if typer.confirm("Preview a limit/net price change for this order?", default=False):
                new_price = _prompt_positive_decimal("New limit/net price")
                _apply_change_price(builder, preview_request, new_price)
                change_client_order_id = _new_demo_client_order_id()
                builder.client_order_id(change_client_order_id)
                typer.echo(f"Change client order ID: {change_client_order_id}")
                change_preview_request = builder.build_change_preview_request(order_id)
                typer.echo("Generated change preview request:")
                _echo_json(change_preview_request.request_body())
                change_preview = await client.orders.preview_change(
                    account_id_key, order_id, change_preview_request
                )
                typer.echo("Change preview response:")
                _echo_preview_order(change_preview)
                change_preview_ids = _preview_ids(change_preview)
                if change_preview_ids and _confirm_live_action("place this order change", settings):
                    change_place = await client.orders.place_change(
                        account_id_key,
                        order_id,
                        builder.build_change_place_request(change_preview_ids, order_id),
                    )
                    typer.echo("Change place response:")
                    _echo_place_order(change_place)
                    changed_order_id = _first_order_id(change_place)
                    if changed_order_id is not None:
                        order_id = changed_order_id
                        typer.echo(f"Current order ID: {order_id}")
                elif not change_preview_ids:
                    typer.echo("No change preview IDs were returned; skipping change placement.")
                else:
                    typer.echo("Order change placement skipped.")

            if typer.confirm("Cancel this order?", default=False):
                if _confirm_live_action("cancel this order", settings):
                    cancel = await client.orders.cancel(account_id_key, order_id)
                    typer.echo("Cancel response:")
                    _echo_cancel_order(cancel)
                else:
                    typer.echo("Order cancellation skipped.")

    _handle(command())


@market_app.command("quote")
def market_quote(
    symbol: str = typer.Argument(..., help="Equity, index, mutual fund, or option symbol."),
    profile: str = typer.Option("default", "--profile", "-p"),
    detail_flag: str | None = typer.Option(None, "--detail-flag"),
    require_earnings_date: bool | None = typer.Option(
        None, "--require-earnings-date/--no-require-earnings-date"
    ),
    skip_mini_options_check: bool | None = typer.Option(
        None, "--skip-mini-options-check/--check-mini-options"
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the full response as JSON."),
) -> None:
    """Show a market quote."""

    async def command() -> None:
        request = QuotesRequest(
            detail_flag=detail_flag,
            require_earnings_date=require_earnings_date,
            skip_mini_options_check=skip_mini_options_check,
        )
        async with ETradeClient(_settings(), profile=profile) as client:
            quote = await client.market.get_quote(symbol, request)
            if json_output:
                _echo_json(quote)
                return
            _echo_quote(quote)

    _handle(command())


@market_app.command("quotes")
def market_quotes(
    symbols: Annotated[list[str], typer.Argument(help="One or more market symbols.")],
    profile: str = typer.Option("default", "--profile", "-p"),
    detail_flag: str | None = typer.Option(None, "--detail-flag"),
    override_symbol_count: bool | None = typer.Option(
        None, "--override-symbol-count/--no-override-symbol-count"
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the full response as JSON."),
) -> None:
    """Show market quotes for one or more symbols."""

    async def command() -> None:
        request = QuotesRequest(
            detail_flag=detail_flag,
            override_symbol_count=override_symbol_count,
        )
        async with ETradeClient(_settings(), profile=profile) as client:
            response = await client.market.get_quotes(symbols, request)
            if json_output:
                _echo_json(response)
                return
            _echo_quotes(response)

    _handle(command())


@market_app.command("lookup")
def market_lookup(
    search: str = typer.Argument(..., help="Company name search text."),
    profile: str = typer.Option("default", "--profile", "-p"),
    json_output: bool = typer.Option(False, "--json", help="Print the full response as JSON."),
) -> None:
    """Look up products by company name."""

    async def command() -> None:
        async with ETradeClient(_settings(), profile=profile) as client:
            response = await client.market.lookup_product(search)
            if json_output:
                _echo_json(response)
                return
            _echo_product_lookup(response)

    _handle(command())


@market_app.command("option-expirations")
def market_option_expirations(
    symbol: str = typer.Argument(..., help="Underlying market symbol."),
    profile: str = typer.Option("default", "--profile", "-p"),
    expiry_type: str | None = typer.Option(None, "--expiry-type"),
    json_output: bool = typer.Option(False, "--json", help="Print the full response as JSON."),
) -> None:
    """Show option expiration dates for an underlying symbol."""

    async def command() -> None:
        request = OptionExpirationsRequest(expiry_type=expiry_type)
        async with ETradeClient(_settings(), profile=profile) as client:
            response = await client.market.get_option_expirations(symbol, request)
            if json_output:
                _echo_json(response)
                return
            _echo_option_expirations(response)

    _handle(command())


@market_app.command("option-chain")
def market_option_chain(
    symbol: str = typer.Argument(..., help="Underlying market symbol."),
    profile: str = typer.Option("default", "--profile", "-p"),
    expiry_year: int | None = typer.Option(None, "--expiry-year"),
    expiry_month: int | None = typer.Option(None, "--expiry-month"),
    expiry_day: int | None = typer.Option(None, "--expiry-day"),
    strike_price_near: str | None = typer.Option(None, "--strike-price-near"),
    no_of_strikes: int | None = typer.Option(None, "--no-of-strikes"),
    chain_type: str | None = typer.Option(None, "--chain-type"),
    option_category: str | None = typer.Option(None, "--option-category"),
    price_type: str | None = typer.Option(None, "--price-type"),
    include_weekly: bool | None = typer.Option(None, "--include-weekly/--exclude-weekly"),
    skip_adjusted: bool | None = typer.Option(None, "--skip-adjusted/--include-adjusted"),
    json_output: bool = typer.Option(False, "--json", help="Print the full response as JSON."),
) -> None:
    """Show an option chain for an underlying symbol."""

    async def command() -> None:
        request = OptionChainRequest(
            expiry_year=expiry_year,
            expiry_month=expiry_month,
            expiry_day=expiry_day,
            strike_price_near=Decimal(strike_price_near) if strike_price_near is not None else None,
            no_of_strikes=no_of_strikes,
            chain_type=chain_type,
            option_category=option_category,
            price_type=price_type,
            include_weekly=include_weekly,
            skip_adjusted=skip_adjusted,
        )
        async with ETradeClient(_settings(), profile=profile) as client:
            response = await client.market.get_option_chain(symbol, request)
            if json_output:
                _echo_json(response)
                return
            _echo_option_chain(response)

    _handle(command())


def _prompt_account(response: AccountListResponse) -> Account:
    accounts = response.accounts
    if not accounts:
        typer.echo("No accounts found.")
        raise typer.Exit(code=1)
    choices = [(_account_label(account), account) for account in accounts]
    return _prompt_menu("Select account", choices)


def _account_label(account: Account) -> str:
    label = account.account_name or account.account_desc or "Account"
    pieces = [label]
    if account.account_type is not None:
        pieces.append(account.account_type)
    pieces.append(f"accountId {_mask_account_id(account.account_id)}")
    pieces.append(f"accountIdKey {account.account_id_key}")
    return " | ".join(pieces)


def _mask_account_id(account_id: str) -> str:
    if len(account_id) <= 4:
        return "*" * len(account_id)
    return "*" * (len(account_id) - 4) + account_id[-4:]


def _prompt_order_scenario() -> str:
    return _prompt_menu(
        "Select order scenario",
        [
            ("Equity limit order", "equity"),
            ("Single-leg option order", "single-option"),
            ("Vertical call spread", "vertical"),
            ("Three-leg call spread + short put", "three-leg"),
            ("Iron condor", "iron-condor"),
            ("Buy-write", "buy-write"),
        ],
    )


async def _build_demo_order(
    client: ETradeClient, account_id_key: str, scenario: str
) -> OrderBuilder:
    builder = OrderBuilder.for_account(account_id_key).client_order_id(_prompt_client_order_id())
    if scenario == "equity":
        return builder.equity_limit(
            _prompt_symbol(),
            action=_prompt_menu(
                "Equity action",
                [
                    ("Buy", "BUY"),
                    ("Sell", "SELL"),
                    ("Sell short", "SELL_SHORT"),
                    ("Buy to cover", "BUY_TO_COVER"),
                ],
            ),
            quantity=_prompt_positive_decimal("Quantity", "1"),
            limit_price=_prompt_positive_decimal("Limit price"),
        )

    symbol = _prompt_symbol()
    expiration = await _prompt_option_expiration(client, symbol)
    chain = await _get_option_chain(client, symbol, expiration)

    if scenario == "single-option":
        option_action = _prompt_menu(
            "Option action",
            [
                ("Long call", "long-call"),
                ("Short call", "short-call"),
                ("Long put", "long-put"),
                ("Short put", "short-put"),
            ],
        )
        option_side = _option_side(option_action)
        strike, contract = _prompt_option_contract(chain, option_side, "Strike price")
        quantity = _prompt_positive_decimal("Contracts", "1")
        suggested = (
            _contract_ask(contract) if option_action.startswith("long") else _contract_bid(contract)
        )
        limit_price = _prompt_limit_with_suggestion("Limit price", suggested)
        builder.order_type("OPTN").with_symbol(symbol).with_expiration(expiration).limit_price(
            limit_price
        )
        if option_action == "long-call":
            return builder.add_long_call(strike, quantity)
        if option_action == "short-call":
            return builder.add_short_call(strike, quantity)
        if option_action == "long-put":
            return builder.add_long_put(strike, quantity)
        return builder.add_short_put(strike, quantity)

    if scenario == "vertical":
        quantity = _prompt_positive_decimal("Contracts", "1")
        long_strike, long_call = _prompt_option_contract(chain, "CALL", "Long call strike")
        short_strike, short_call = _prompt_option_contract(chain, "CALL", "Short call strike")
        signed_estimate = _subtract(_contract_ask(long_call), _contract_bid(short_call))
        price_type, price = _prompt_net_price(signed_estimate, "NET_DEBIT")
        builder.order_type("SPREADS").with_symbol(symbol).with_expiration(expiration)
        _apply_net_price(builder, price_type, price)
        return builder.add_long_call(long_strike, quantity).add_short_call(short_strike, quantity)

    if scenario == "three-leg":
        quantity = _prompt_positive_decimal("Contracts", "1")
        long_call_strike, long_call = _prompt_option_contract(chain, "CALL", "Long call strike")
        short_call_strike, short_call = _prompt_option_contract(chain, "CALL", "Short call strike")
        short_put_strike, short_put = _prompt_option_contract(chain, "PUT", "Short put strike")
        signed_estimate = _subtract(
            _subtract(_contract_ask(long_call), _contract_bid(short_call)),
            _contract_bid(short_put),
        )
        price_type, price = _prompt_net_price(signed_estimate, "NET_DEBIT")
        builder.order_type("SPREADS").with_symbol(symbol).with_expiration(expiration)
        _apply_net_price(builder, price_type, price)
        return (
            builder.add_long_call(long_call_strike, quantity)
            .add_short_call(short_call_strike, quantity)
            .add_short_put(short_put_strike, quantity)
        )

    if scenario == "iron-condor":
        quantity = _prompt_positive_decimal("Contracts", "1")
        short_put_strike, short_put = _prompt_option_contract(chain, "PUT", "Short put strike")
        long_put_strike, long_put = _prompt_option_contract(chain, "PUT", "Long put strike")
        short_call_strike, short_call = _prompt_option_contract(chain, "CALL", "Short call strike")
        long_call_strike, long_call = _prompt_option_contract(chain, "CALL", "Long call strike")
        signed_estimate = _add(
            _subtract(_contract_bid(short_put), _contract_ask(long_put)),
            _subtract(_contract_bid(short_call), _contract_ask(long_call)),
        )
        price_type, price = _prompt_net_price(signed_estimate, "NET_CREDIT")
        builder.order_type("SPREADS").with_symbol(symbol).with_expiration(expiration)
        _apply_net_price(builder, price_type, price)
        return (
            builder.add_short_put(short_put_strike, quantity)
            .add_long_put(long_put_strike, quantity)
            .add_short_call(short_call_strike, quantity)
            .add_long_call(long_call_strike, quantity)
        )

    if scenario == "buy-write":
        stock_quantity, call_quantity = _prompt_buy_write_quantities()
        call_strike, call = _prompt_option_contract(chain, "CALL", "Call strike")
        quote = await _get_quote(client, symbol)
        suggested = _buy_write_estimate(quote, stock_quantity, call, call_quantity)
        net_debit = _prompt_limit_with_suggestion("Net debit", suggested)
        return builder.buy_write(
            symbol,
            expiration=expiration,
            stock_quantity=stock_quantity,
            call_quantity=call_quantity,
            call_strike=call_strike,
            net_debit=net_debit,
        )
    raise typer.BadParameter("Unknown order scenario")


async def _prompt_option_expiration(client: ETradeClient, symbol: str) -> date:
    expirations = await _get_option_expirations(client, symbol)
    if expirations:
        return _prompt_expiration_choice(expirations)
    fallback = _next_third_friday()
    typer.echo(f"No option expirations found; using third-Friday fallback {fallback}.")
    return _prompt_expiration(fallback)


async def _get_option_expirations(client: ETradeClient, symbol: str) -> list[OptionExpiration]:
    try:
        response = await client.market.get_option_expirations(
            symbol, OptionExpirationsRequest(expiry_type="ALL")
        )
    except ETradeError as exc:
        typer.echo(f"Could not fetch option expirations: {exc}")
        return []
    today = date.today()
    expirations: list[OptionExpiration] = []
    for expiration in response.expiration_dates:
        if expiration.year is None or expiration.month is None or expiration.day is None:
            continue
        try:
            expiration_date = date(expiration.year, expiration.month, expiration.day)
        except ValueError:
            continue
        if expiration_date >= today:
            expirations.append(expiration)
    return sorted(expirations, key=_expiration_sort_key)


def _prompt_expiration_choice(expirations: list[OptionExpiration]) -> date:
    default_index = _default_expiration_index(expirations)
    typer.echo("Available expirations:")
    for index, expiration in enumerate(expirations[:10], start=1):
        expiration_date = _expiration_date(expiration)
        label = expiration_date.isoformat() if expiration_date is not None else "Expiration"
        suffix = f" {expiration.expiry_type}" if expiration.expiry_type else ""
        default_marker = " [default]" if index - 1 == default_index else ""
        typer.echo(f"  {index}. {label}{suffix}{default_marker}")
    while True:
        selected = typer.prompt("Expiration", default=str(default_index + 1)).strip()
        try:
            index = int(selected)
        except ValueError:
            typer.echo("Enter a numbered expiration.")
            continue
        if 1 <= index <= min(len(expirations), 10):
            expiration_date = _expiration_date(expirations[index - 1])
            if expiration_date is not None:
                return expiration_date
        typer.echo("Enter a numbered expiration from the list.")


def _default_expiration_index(expirations: list[OptionExpiration]) -> int:
    for index, expiration in enumerate(expirations):
        if (expiration.expiry_type or "").upper() == "MONTHLY":
            return index
    return 0


def _expiration_sort_key(expiration: OptionExpiration) -> tuple[int, int, int]:
    return (expiration.year or 9999, expiration.month or 12, expiration.day or 31)


def _expiration_date(expiration: OptionExpiration) -> date | None:
    if expiration.year is None or expiration.month is None or expiration.day is None:
        return None
    try:
        return date(expiration.year, expiration.month, expiration.day)
    except ValueError:
        return None


def _next_third_friday() -> date:
    today = date.today()
    year = today.year
    month = today.month
    while True:
        candidate = _third_friday(year, month)
        if candidate >= today:
            return candidate
        month += 1
        if month > 12:
            month = 1
            year += 1


def _third_friday(year: int, month: int) -> date:
    first_day = date(year, month, 1)
    days_until_friday = (4 - first_day.weekday()) % 7
    first_friday = first_day.replace(day=1 + days_until_friday)
    return first_friday.replace(day=first_friday.day + 14)


async def _get_option_chain(
    client: ETradeClient, symbol: str, expiration: date
) -> OptionChainResponse | None:
    try:
        return await client.market.get_option_chain(
            symbol,
            OptionChainRequest(
                expiry_year=expiration.year,
                expiry_month=expiration.month,
                expiry_day=expiration.day,
                chain_type="CALLPUT",
                price_type="ALL",
            ),
        )
    except ETradeError as exc:
        typer.echo(f"Could not fetch option chain: {exc}")
        return None


async def _get_quote(client: ETradeClient, symbol: str) -> Quote | None:
    try:
        return await client.market.get_quote(symbol)
    except ETradeError as exc:
        typer.echo(f"Could not fetch quote: {exc}")
        return None


def _find_option_contract(
    chain: OptionChainResponse | None, call_put: str, strike: Decimal
) -> OptionContract | None:
    if chain is None:
        return None
    for pair in chain.option_pairs:
        contract = pair.call if call_put == "CALL" else pair.put
        if contract is not None and contract.strike_price == strike:
            return contract
    typer.echo(f"No {call_put.lower()} quote found for strike {strike}; enter price manually.")
    return None


def _prompt_option_contract(
    chain: OptionChainResponse | None, call_put: str, label: str
) -> tuple[Decimal, OptionContract | None]:
    contracts = _option_contracts(chain, call_put)
    if not contracts:
        strike = _prompt_positive_decimal(label)
        return strike, _find_option_contract(chain, call_put, strike)

    visible_contracts = _visible_option_contracts(contracts, chain.near_price if chain else None)
    default_index = _default_contract_index(visible_contracts, chain.near_price if chain else None)
    typer.echo(f"Available {call_put.lower()} strikes:")
    for index, contract in enumerate(visible_contracts, start=1):
        strike = _format_decimal(contract.strike_price) or "Strike"
        default_marker = " [default]" if index - 1 == default_index else ""
        bid = _format_decimal(contract.bid) or "-"
        ask = _format_decimal(contract.ask) or "-"
        typer.echo(f"  {index}. {strike} Bid {bid} Ask {ask}{default_marker}")

    while True:
        selected = typer.prompt(label, default=str(default_index + 1)).strip()
        try:
            index = int(selected)
        except ValueError:
            typer.echo("Enter a numbered strike.")
            continue
        if 1 <= index <= len(visible_contracts):
            contract = visible_contracts[index - 1]
            if contract.strike_price is not None:
                return contract.strike_price, contract
        typer.echo("Enter a numbered strike from the list.")


def _option_contracts(chain: OptionChainResponse | None, call_put: str) -> list[OptionContract]:
    if chain is None:
        return []
    contracts_by_strike: dict[Decimal, OptionContract] = {}
    for pair in chain.option_pairs:
        contract = pair.call if call_put == "CALL" else pair.put
        if contract is None or contract.strike_price is None:
            continue
        contracts_by_strike.setdefault(contract.strike_price, contract)
    return [contracts_by_strike[strike] for strike in sorted(contracts_by_strike)]


def _visible_option_contracts(
    contracts: list[OptionContract], near_price: Decimal | None
) -> list[OptionContract]:
    if len(contracts) <= 11 or near_price is None:
        return contracts

    at_the_money_index = _default_contract_index(contracts, near_price)
    start = max(0, at_the_money_index - 5)
    end = min(len(contracts), at_the_money_index + 6)
    return contracts[start:end]


def _default_contract_index(contracts: list[OptionContract], near_price: Decimal | None) -> int:
    if not contracts or near_price is None:
        return 0
    return min(
        range(len(contracts)),
        key=lambda index: abs((contracts[index].strike_price or near_price) - near_price),
    )


def _contract_bid(contract: OptionContract | None) -> Decimal | None:
    return contract.bid if contract is not None else None


def _contract_ask(contract: OptionContract | None) -> Decimal | None:
    return contract.ask if contract is not None else None


def _option_side(option_action: str) -> str:
    return "PUT" if option_action.endswith("put") else "CALL"


def _prompt_limit_with_suggestion(label: str, suggested: Decimal | None) -> Decimal:
    default = _format_decimal(suggested) if suggested is not None and suggested > 0 else None
    if suggested is not None and suggested > 0:
        typer.echo(f"Suggested {label.lower()}: {suggested}")
    return _prompt_positive_decimal(label, default)


def _prompt_net_price(
    signed_estimate: Decimal | None, fallback_price_type: str
) -> tuple[str, Decimal]:
    default_price_type = fallback_price_type
    default_price: Decimal | None = None
    if signed_estimate is not None:
        if signed_estimate < 0:
            default_price_type = "NET_CREDIT"
            default_price = abs(signed_estimate)
            typer.echo(f"Estimated net credit: {default_price}")
        elif signed_estimate > 0:
            default_price_type = "NET_DEBIT"
            default_price = signed_estimate
            typer.echo(f"Estimated net debit: {default_price}")
        else:
            typer.echo("Estimated net even: 0")
    price_type = _prompt_net_price_type(default_price_type)
    label = "Net credit" if price_type == "NET_CREDIT" else "Net debit"
    default = _format_decimal(default_price) if default_price is not None else None
    price = _prompt_positive_decimal(label, default)
    return price_type, price


def _prompt_net_price_type(default: str) -> str:
    while True:
        value = typer.prompt("Price type", default=default).strip().upper()
        if value in {"NET_DEBIT", "NET_CREDIT"}:
            return value
        typer.echo("Price type must be NET_DEBIT or NET_CREDIT.")


def _apply_net_price(builder: OrderBuilder, price_type: str, price: Decimal) -> None:
    if price_type == "NET_CREDIT":
        builder.net_credit(price)
    else:
        builder.net_debit(price)


def _add(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None or right is None:
        return None
    return left + right


def _subtract(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None or right is None:
        return None
    return left - right


def _prompt_buy_write_quantities() -> tuple[Decimal, Decimal]:
    while True:
        stock_quantity = _prompt_positive_decimal("Stock quantity", "100")
        call_quantity = _prompt_positive_decimal("Call contracts", "1")
        if _is_covered_call_ratio(stock_quantity, call_quantity):
            return stock_quantity, call_quantity
        typer.echo("Buy-write quantity must be 100 shares for each short call contract.")


def _is_covered_call_ratio(stock_quantity: Decimal, call_quantity: Decimal) -> bool:
    return stock_quantity == call_quantity * Decimal("100")


def _buy_write_estimate(
    quote: Quote | None,
    stock_quantity: Decimal,
    call: OptionContract | None,
    call_quantity: Decimal,
) -> Decimal | None:
    stock_ask = _quote_ask(quote)
    call_bid = _contract_bid(call)
    if stock_ask is None or call_bid is None or stock_quantity <= 0:
        return None
    total_debit = stock_ask * stock_quantity - call_bid * call_quantity * Decimal("100")
    return total_debit / stock_quantity


def _quote_ask(quote: Quote | None) -> Decimal | None:
    if quote is None:
        return None
    details = quote.all or quote.intraday or quote.fundamental or quote.option or quote.week52
    if details is None:
        return None
    return details.ask


def _format_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f")


def _prompt_client_order_id() -> str:
    default = _new_demo_client_order_id()
    while True:
        value = _prompt_nonempty("Client order ID", default=default)
        if value.isalnum() and len(value) <= 20:
            return value
        typer.echo("Client order ID must be 1-20 alphanumeric characters.")


def _new_demo_client_order_id() -> str:
    return f"epdemo{uuid4().hex[:8]}"


def _prompt_symbol() -> str:
    return _prompt_nonempty("Symbol").upper()


def _prompt_expiration(default: date | None = None) -> date:
    return date(
        _prompt_int("Expiration year", default=default.year if default is not None else None),
        _prompt_int(
            "Expiration month",
            minimum=1,
            maximum=12,
            default=default.month if default is not None else None,
        ),
        _prompt_int(
            "Expiration day",
            minimum=1,
            maximum=31,
            default=default.day if default is not None else None,
        ),
    )


def _prompt_menu(title: str, choices: list[tuple[str, TChoice]]) -> TChoice:
    typer.echo(title)
    for index, (label, _) in enumerate(choices, start=1):
        typer.echo(f"  {index}. {label}")
    while True:
        selected = typer.prompt("Choice")
        try:
            index = int(selected)
        except ValueError:
            typer.echo("Enter a numbered choice.")
            continue
        if 1 <= index <= len(choices):
            return choices[index - 1][1]
        typer.echo("Enter a numbered choice from the menu.")


def _prompt_nonempty(label: str, default: str | None = None) -> str:
    while True:
        value = typer.prompt(label, default=default).strip()
        if value:
            return value
        typer.echo(f"{label} is required.")


def _prompt_int(
    label: str,
    minimum: int | None = None,
    maximum: int | None = None,
    default: int | None = None,
) -> int:
    while True:
        raw = typer.prompt(label, default=str(default) if default is not None else None).strip()
        try:
            value = int(raw)
        except ValueError:
            typer.echo(f"{label} must be an integer.")
            continue
        if minimum is not None and value < minimum:
            typer.echo(f"{label} must be at least {minimum}.")
            continue
        if maximum is not None and value > maximum:
            typer.echo(f"{label} must be at most {maximum}.")
            continue
        return value


def _prompt_positive_decimal(label: str, default: str | None = None) -> Decimal:
    while True:
        raw = typer.prompt(label, default=default).strip()
        try:
            value = Decimal(raw)
        except InvalidOperation:
            typer.echo(f"{label} must be a decimal number.")
            continue
        if value <= 0:
            typer.echo(f"{label} must be greater than zero.")
            continue
        return value


def _preview_ids(response: PreviewOrderResponse) -> list[int]:
    return [item.preview_id for item in response.preview_ids]


def _first_order_id(response: PlaceOrderResponse) -> int | None:
    if not response.order_ids:
        return None
    return response.order_ids[0].order_id


def _apply_change_price(
    builder: OrderBuilder, preview_request: PreviewOrderRequest, new_price: Decimal
) -> None:
    price_type = preview_request.orders[0].price_type if preview_request.orders else "LIMIT"
    if price_type == "NET_CREDIT":
        builder.net_credit(new_price)
    elif price_type == "NET_DEBIT":
        builder.net_debit(new_price)
    else:
        builder.limit_price(new_price)


def _confirm_live_action(action: str, settings: ETradeSettings) -> bool:
    if settings.environment.value == "production":
        typer.echo("Production environment: this action affects a real brokerage account.")
    return typer.confirm(f"Confirm that you want to {action}?", default=False)


def _load_model_file(path: Path, model_type: type[TModel], envelope: str) -> TModel:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise typer.BadParameter("Expected a readable JSON request file") from None
    if isinstance(payload, dict):
        payload_mapping = cast(dict[str, Any], payload)
        if envelope in payload_mapping:
            payload = payload_mapping[envelope]
    try:
        return model_type.model_validate(payload)
    except ValueError as exc:
        raise typer.BadParameter("Invalid order request JSON") from exc


def _require_live_order_confirmation(confirmed: bool) -> None:
    if not confirmed:
        typer.echo("Order mutation commands require --confirm-live-order.", err=True)
        raise typer.Exit(code=1)


def _echo_json(value: BaseModel | dict[str, Any]) -> None:
    if isinstance(value, BaseModel):
        typer.echo(value.model_dump_json(by_alias=True, exclude_none=True, indent=2))
        return
    typer.echo(json.dumps(value, indent=2))


def _echo_account_list(response: AccountListResponse) -> None:
    if not response.accounts:
        typer.echo("No accounts found.")
        return
    for account in response.accounts:
        label = account.account_name or account.account_desc or "Account"
        typer.echo(label)
        typer.echo(f"  Account ID: {account.account_id}")
        typer.echo(f"  Account ID key: {account.account_id_key}")
        _echo_optional("  Type", account.account_type)
        _echo_optional("  Status", account.account_status)


def _echo_account_balance(response: AccountBalanceResponse) -> None:
    typer.echo(f"Account ID: {response.account_id}")
    _echo_optional("Account type", response.account_type)
    _echo_optional("Description", response.account_description or response.account_desc)
    _echo_optional("Day trader status", response.day_trader_status)
    if response.computed_balance is not None:
        computed = response.computed_balance
        _echo_optional_decimal("Net cash", computed.net_cash)
        _echo_optional_decimal("Cash balance", computed.cash_balance)
        _echo_optional_decimal("Cash buying power", computed.cash_buying_power)
        _echo_optional_decimal("Margin buying power", computed.margin_buying_power)
        _echo_optional_decimal(
            "Total available for withdrawal", computed.total_available_for_withdrawal
        )
    if response.cash is not None:
        _echo_optional_decimal("Money market balance", response.cash.money_market_balance)
    if response.margin is not None:
        _echo_optional_decimal(
            "Day-trade margin open order reserve",
            response.margin.dt_margin_open_order_reserve,
        )


def _echo_portfolio(response: PortfolioResponse) -> None:
    if response.totals is not None:
        _echo_optional_decimal("Total market value", response.totals.total_market_value)
        _echo_optional_decimal("Total gain/loss", response.totals.total_gain_loss)
    positions = [
        position
        for account_portfolio in response.account_portfolios
        for position in account_portfolio.positions
    ]
    if not positions:
        typer.echo("No positions found.")
        return
    for position in positions:
        symbol = position.product.symbol if position.product is not None else None
        typer.echo(symbol or position.symbol_description or "Position")
        _echo_optional("  Position ID", position.position_id)
        _echo_optional("  Type", position.position_type)
        _echo_optional_decimal("  Quantity", position.quantity)
        _echo_optional_decimal("  Market value", position.market_value)
        _echo_optional_decimal("  Total gain", position.total_gain)


def _echo_transactions(response: TransactionsResponse) -> None:
    if not response.transactions:
        typer.echo("No transactions found.")
        return
    for transaction in response.transactions:
        typer.echo(transaction.description or transaction.transaction_id or "Transaction")
        _echo_optional("  Transaction ID", transaction.transaction_id)
        _echo_optional("  Date", transaction.transaction_date)
        _echo_optional_decimal("  Amount", transaction.amount)
        _echo_optional("  Type", transaction.transaction_type)


def _echo_transaction_details(response: TransactionDetailsResponse) -> None:
    transaction = response.transaction
    typer.echo(transaction.description or transaction.transaction_id or "Transaction")
    _echo_optional("Transaction ID", transaction.transaction_id)
    _echo_optional("Account ID", transaction.account_id)
    _echo_optional("Date", transaction.transaction_date)
    _echo_optional_decimal("Amount", transaction.amount)
    if transaction.brokerage is not None:
        _echo_optional("Brokerage type", transaction.brokerage.transaction_type)
        if transaction.brokerage.product is not None:
            _echo_optional("Symbol", transaction.brokerage.product.symbol)
        _echo_optional_decimal("Quantity", transaction.brokerage.quantity)
        _echo_optional_decimal("Price", transaction.brokerage.price)


def _echo_orders(response: OrdersResponse) -> None:
    if not response.orders:
        typer.echo("No orders found.")
        return
    for order in response.orders:
        typer.echo(f"Order ID: {order.order_id}")
        _echo_optional("  Type", order.order_type)
        _echo_optional_decimal("  Total value", order.total_order_value)
        _echo_optional_decimal("  Commission", order.total_commission)
        if order.order_details:
            detail = order.order_details[0]
            _echo_optional("  Status", detail.status)
            _echo_optional("  Term", detail.order_term)
            _echo_optional("  Price type", detail.price_type)
            if detail.instruments and detail.instruments[0].product is not None:
                _echo_optional("  Symbol", detail.instruments[0].product.symbol)


def _echo_preview_order(response: PreviewOrderResponse) -> None:
    typer.echo(response.order_type or "Preview order")
    _echo_optional_decimal("Total order value", response.total_order_value)
    if response.preview_ids:
        typer.echo(
            "Preview IDs: " + ", ".join(str(item.preview_id) for item in response.preview_ids)
        )
    for order in response.orders:
        _echo_optional("Price type", order.price_type)
        _echo_optional_decimal("Limit price", order.limit_price)
        _echo_optional_decimal("Estimated total", order.estimated_total_amount)
        if order.messages is not None:
            for message in order.messages.messages:
                _echo_optional("Message", message.description)


def _echo_place_order(response: PlaceOrderResponse) -> None:
    typer.echo(response.order_type or "Placed order")
    if response.order_ids:
        typer.echo("Order IDs: " + ", ".join(str(item.order_id) for item in response.order_ids))
    for order in response.orders:
        _echo_optional("Price type", order.price_type)
        _echo_optional_decimal("Limit price", order.limit_price)
        _echo_optional_decimal("Estimated total", order.estimated_total_amount)
        if order.messages is not None:
            for message in order.messages.messages:
                _echo_optional("Message", message.description)


def _echo_cancel_order(response: CancelOrderResponse) -> None:
    _echo_optional("Account ID", response.account_id)
    _echo_optional("Order ID", response.order_id)
    _echo_optional("Cancel time", response.cancel_time)
    if response.messages is not None:
        for message in response.messages.messages:
            _echo_optional("Message", message.description)


def _echo_quote(quote: Quote) -> None:
    symbol = quote.product.symbol if quote.product is not None else None
    details = quote.all or quote.intraday or quote.fundamental or quote.option or quote.week52
    typer.echo(symbol or "Quote")
    _echo_optional("  Status", quote.quote_status)
    if details is not None:
        _echo_optional("  Company", details.company_name or details.symbol_description)
        _echo_optional_decimal("  Last trade", details.last_trade)
        _echo_optional_decimal("  Bid", details.bid)
        _echo_optional_decimal("  Ask", details.ask)
        _echo_optional_decimal("  Change", details.change_close)
        _echo_optional("  Volume", details.total_volume)


def _echo_quotes(response: QuotesResponse) -> None:
    if not response.quotes:
        typer.echo("No quotes found.")
        return
    for quote in response.quotes:
        _echo_quote(quote)


def _echo_product_lookup(response: ProductLookupResponse) -> None:
    if not response.products:
        typer.echo("No products found.")
        return
    for product in response.products:
        typer.echo(product.symbol or "Product")
        _echo_optional("  Description", product.description)
        _echo_optional("  Type", product.type)


def _echo_option_expirations(response: OptionExpirationsResponse) -> None:
    if not response.expiration_dates:
        typer.echo("No option expirations found.")
        return
    for expiration in response.expiration_dates:
        if expiration.year is None or expiration.month is None or expiration.day is None:
            typer.echo("Expiration")
        else:
            typer.echo(f"{expiration.year:04d}-{expiration.month:02d}-{expiration.day:02d}")
        _echo_optional("  Type", expiration.expiry_type)


def _echo_option_chain(response: OptionChainResponse) -> None:
    _echo_optional("Quote type", response.quote_type)
    _echo_optional_decimal("Near price", response.near_price)
    if not response.option_pairs:
        typer.echo("No option pairs found.")
        return
    for pair in response.option_pairs:
        if pair.call is not None:
            typer.echo(pair.call.display_symbol or pair.call.osi_key or "Call")
            _echo_optional_decimal("  Strike", pair.call.strike_price)
            _echo_optional_decimal("  Bid", pair.call.bid)
            _echo_optional_decimal("  Ask", pair.call.ask)
        if pair.put is not None:
            typer.echo(pair.put.display_symbol or pair.put.osi_key or "Put")
            _echo_optional_decimal("  Strike", pair.put.strike_price)
            _echo_optional_decimal("  Bid", pair.put.bid)
            _echo_optional_decimal("  Ask", pair.put.ask)


def _echo_optional(label: str, value: object | None) -> None:
    if value is not None:
        typer.echo(f"{label}: {value}")


def _echo_optional_decimal(label: str, value: Decimal | None) -> None:
    if value is not None:
        typer.echo(f"{label}: {value}")


def _handle(coro: Coroutine[Any, Any, object]) -> None:
    try:
        _run(coro)
    except ETradeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
