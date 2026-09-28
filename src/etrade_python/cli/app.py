"""Diagnostic CLI for authentication bootstrap and read-only API checks."""

import asyncio
from collections.abc import Coroutine
from decimal import Decimal
from typing import Any

import typer
from pydantic import BaseModel

from etrade_python import (
    AccountBalanceRequest,
    AccountBalanceResponse,
    AccountListResponse,
    __version__,
)
from etrade_python.auth import TokenStatus
from etrade_python.client import ETradeClient
from etrade_python.config import ETradeSettings
from etrade_python.exceptions import ETradeError

app = typer.Typer(no_args_is_help=True, invoke_without_command=True)
auth_app = typer.Typer(no_args_is_help=True)
accounts_app = typer.Typer(no_args_is_help=True)
app.add_typer(auth_app, name="auth")
app.add_typer(accounts_app, name="accounts")


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
