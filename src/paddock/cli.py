"""The paddock CLI: subcommands over a docker-compose-managed agent container."""

from __future__ import annotations

import os
from importlib.metadata import version as _pkg_version
from typing import NoReturn

import typer

from . import compose, paths

app = typer.Typer(add_completion=False, help=__doc__, no_args_is_help=False)

DEFAULT_SSH_PORT = "2222"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(_pkg_version("paddock"))
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the paddock version and exit.",
    ),
) -> None:
    """Build, start, stop, and manage the paddock container via docker compose."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(code=0)


def _fail(message: str) -> NoReturn:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def _run_compose(subcommand_args: list[str], *, refresh_tools: bool = False) -> None:
    try:
        compose.run(compose.compose_args(subcommand_args), compose.interpolation_env(refresh_tools))
    except compose.ComposeError as exc:
        _fail(str(exc))


def _exec_compose(subcommand_args: list[str]) -> NoReturn:
    try:
        compose.exec_(
            compose.compose_args(subcommand_args), compose.interpolation_env(refresh_tools=False)
        )
    except compose.ComposeError as exc:
        _fail(str(exc))


def _resolve_ssh_port() -> str:
    """Resolve the published ssh port using compose's own interpolation precedence.

    Shell environment wins (matching ``interpolation_env``'s pass-through
    behavior), then the config dir's ``.env`` (compose's ``--env-file``),
    then the packaged compose file's own default.
    """
    if "PADDOCK_SSH_PORT" in os.environ:
        return os.environ["PADDOCK_SSH_PORT"]
    env_file = paths.env_file()
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "PADDOCK_SSH_PORT":
                return value.strip()
    return DEFAULT_SSH_PORT


@app.command()
def build(
    cached: bool = typer.Option(
        False,
        "--cached",
        help="Pin PADDOCK_TOOLS_REFRESH to 0, reusing the cached tool-install layer.",
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache", help="Full rebuild: pass --no-cache through to docker compose build."
    ),
) -> None:
    """Build the image."""
    args = ["build"]
    if no_cache:
        args.append("--no-cache")
    _run_compose(args, refresh_tools=not cached)


@app.command()
def up(
    build: bool = typer.Option(False, "--build", help="Build the image first."),
    cached: bool = typer.Option(
        False,
        "--cached",
        help="With --build, pin PADDOCK_TOOLS_REFRESH to 0 instead of refreshing.",
    ),
) -> None:
    """Start the container in the background."""
    args = ["up", "-d"]
    if build:
        args.append("--build")
    _run_compose(args, refresh_tools=build and not cached)


@app.command()
def down(
    volumes: bool = typer.Option(
        False,
        "--volumes",
        help="Also remove volumes. Destroys agent_home: tool auth, shell history, dotfiles.",
    ),
) -> None:
    """Stop and remove the container."""
    args = ["down"]
    if volumes:
        args.append("-v")
    _run_compose(args)


@app.command()
def start() -> None:
    """Start the container."""
    _run_compose(["start"])


@app.command()
def stop() -> None:
    """Stop the container."""
    _run_compose(["stop"])


@app.command()
def restart() -> None:
    """Restart the container."""
    _run_compose(["restart"])


@app.command()
def status() -> None:
    """Show container status, including the published ssh port."""
    typer.echo(f"ssh port: {_resolve_ssh_port()}")
    _run_compose(["ps"])


@app.command()
def logs(
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output."),
) -> None:
    """Show container logs."""
    args = ["logs"]
    if follow:
        args.append("-f")
    _exec_compose(args)


@app.command(
    "compose",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    add_help_option=False,
    help="Passthrough to docker compose, e.g. `paddock compose -- exec agent zsh`.",
)
def compose_passthrough(ctx: typer.Context) -> None:
    _exec_compose(ctx.args)
