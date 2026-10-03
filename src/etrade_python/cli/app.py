"""Diagnostic CLI for authentication bootstrap and read-only API checks."""

import asyncio
from collections.abc import Coroutine
from decimal import Decimal
from typing import Annotated, Any

import typer
from pydantic import BaseModel

from etrade_python import (
    AccountBalanceRequest,
    AccountBalanceResponse,
    AccountListResponse,
    OptionChainRequest,
    OptionChainResponse,
    OptionExpirationsRequest,
    OptionExpirationsResponse,
    PortfolioRequest,
    PortfolioResponse,
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

app = typer.Typer(no_args_is_help=True, invoke_without_command=True)
auth_app = typer.Typer(no_args_is_help=True)
accounts_app = typer.Typer(no_args_is_help=True)
portfolio_app = typer.Typer(no_args_is_help=True)
transactions_app = typer.Typer(no_args_is_help=True)
market_app = typer.Typer(no_args_is_help=True)
app.add_typer(auth_app, name="auth")
app.add_typer(accounts_app, name="accounts")
app.add_typer(portfolio_app, name="portfolio")
app.add_typer(transactions_app, name="transactions")
app.add_typer(market_app, name="market")


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


def _echo_json(model: BaseModel) -> None:
    typer.echo(model.model_dump_json(by_alias=True, exclude_none=True, indent=2))


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
