"""The paddock CLI: a thin ``docker compose`` passthrough for the agent container.

paddock wraps no compose verb. Everything after ``--`` is handed to
``docker compose`` as-is, with paddock supplying only the file assembly
(packaged base compose file, optional per-machine override, optional
``--env-file``) and the ``PADDOCK_*`` interpolation variables. The one thing
that isn't a compose verb, scaffolding the config directory, is ``--init``.
"""

from __future__ import annotations

import sys
from importlib.metadata import version as _pkg_version
from typing import Annotated, NoReturn

import typer

from . import compose, paths

app = typer.Typer(add_completion=False)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(_pkg_version("paddock"))
        raise typer.Exit()


def _fail(message: str) -> NoReturn:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def _passthrough_args(argv: list[str]) -> list[str] | None:
    """Return the args following the first ``--``, or None when there is no ``--``.

    Click consumes the ``--`` separator without recording that it saw one, so
    the parsed arguments alone can't tell ``paddock -- start`` from
    ``paddock start``. This reads ``sys.argv`` to answer that question; when a
    separator is present the slice it returns matches Click's own parse.
    """
    if "--" not in argv:
        return None
    return argv[argv.index("--") + 1 :]


def _init() -> None:
    """Scaffold the config directory."""
    config_dir = paths.config_dir()
    certs_dir = paths.certs_dir()

    created = [d for d in (config_dir, certs_dir) if not d.exists()]
    for d in created:
        d.mkdir(parents=True)

    if created:
        typer.echo("Created:")
        for d in created:
            typer.echo(f"  {d}")
    else:
        typer.echo(f"{config_dir} already exists; nothing to do.")

    authorized_keys = paths.authorized_keys_path()
    if not authorized_keys.exists():
        typer.echo(f"\nAdd your public key(s) to {authorized_keys} to ssh in, e.g.:")
        typer.echo(f"  ssh-add -L >> {authorized_keys}")


def _warn_if_no_authorized_keys() -> None:
    """Warn before a compose call that may start a container refusing every key.

    ``interpolation_env`` always sets ``PADDOCK_AUTHORIZED_KEYS`` to this path
    whether or not the file exists, so a missing file is not a compose error.
    The container starts and sshd runs; it just has no keys to accept.
    """
    authorized_keys = paths.authorized_keys_path()
    if not authorized_keys.exists():
        typer.secho(
            f"warning: {authorized_keys} does not exist; "
            "the container will start but accept no ssh key",
            fg=typer.colors.YELLOW,
            err=True,
        )


@app.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
def paddock(
    ctx: typer.Context,
    args: Annotated[
        list[str] | None,
        typer.Argument(help="Arguments passed straight to docker compose, after a `--`."),
    ] = None,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the paddock version and exit.",
        ),
    ] = False,
    init: Annotated[
        bool, typer.Option("--init", help="Scaffold the config directory, then continue.")
    ] = False,
    refresh: Annotated[
        bool,
        typer.Option(
            "--refresh/--no-refresh",
            help="Set PADDOCK_TOOLS_REFRESH so a build reinstalls the fast-moving tools.",
        ),
    ] = True,
) -> None:
    """Run docker compose against the paddock container, e.g. `paddock -- up -d`."""
    passthrough = _passthrough_args(sys.argv[1:])

    if init:
        _init()

    if args and passthrough is None:
        _fail("compose arguments must follow '--', e.g. `paddock -- up -d`")

    if not passthrough:
        if init:
            raise typer.Exit(code=0)
        typer.echo(ctx.get_help())
        raise typer.Exit(code=0)

    _warn_if_no_authorized_keys()
    try:
        compose.exec_(
            compose.compose_args(passthrough), compose.interpolation_env(refresh_tools=refresh)
        )
    except compose.ComposeError as exc:
        _fail(str(exc))
