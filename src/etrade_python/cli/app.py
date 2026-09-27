"""Diagnostic CLI for authentication bootstrap."""

import asyncio
from collections.abc import Coroutine
from typing import Any

import typer

from etrade_python import __version__
from etrade_python.auth import TokenStatus
from etrade_python.client import ETradeClient
from etrade_python.config import ETradeSettings
from etrade_python.exceptions import ETradeError

app = typer.Typer(no_args_is_help=True, invoke_without_command=True)
auth_app = typer.Typer(no_args_is_help=True)
app.add_typer(auth_app, name="auth")


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


def _handle(coro: Coroutine[Any, Any, object]) -> None:
    try:
        _run(coro)
    except ETradeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
