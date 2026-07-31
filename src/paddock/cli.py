"""The paddock CLI: build, start, stop, restart, and remove the agent container."""

from __future__ import annotations

import shutil
from importlib.metadata import version as _pkg_version
from typing import NoReturn

import typer

from . import config, container, paths

app = typer.Typer(add_completion=False, help=__doc__)

REQUIRED_EXECUTABLES = ["docker"]


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(_pkg_version("paddock"))
        raise typer.Exit()


def _fail(message: str) -> NoReturn:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def _check_dependencies() -> None:
    missing = [exe for exe in REQUIRED_EXECUTABLES if shutil.which(exe) is None]
    if missing:
        _fail(f"required executable(s) not found on PATH: {', '.join(missing)}")


def _load_settings() -> config.Settings:
    try:
        return config.load_settings(paths.config_dir() / "settings.yaml")
    except config.ConfigError as exc:
        _fail(str(exc))


def _build() -> None:
    settings = _load_settings()
    try:
        ca_certificates = config.ca_certificate_paths(settings)
    except config.ConfigError as exc:
        _fail(str(exc))
    try:
        container.build(ca_certificates)
    except container.DockerError as exc:
        _fail(str(exc))


def _start() -> None:
    if not container.image_exists():
        _build()
    authorized_keys = paths.authorized_keys_path()
    settings = _load_settings()
    try:
        env = config.resolve_environment(settings)
    except config.ConfigError as exc:
        _fail(str(exc))
    try:
        container.start(authorized_keys)
        container.set_environment(env)
    except container.DockerError as exc:
        _fail(str(exc))


@app.command()
def main(
    build: bool = typer.Option(False, "--build", help="Build the image."),
    remove: bool = typer.Option(False, "--remove", help="Stop and remove the container and image."),
    start: bool = typer.Option(False, "--start", help="Start the container."),
    stop: bool = typer.Option(False, "--stop", help="Stop the container."),
    restart: bool = typer.Option(False, "--restart", help="Restart the container."),
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the paddock version and exit.",
    ),
) -> None:
    """Build, start, stop, restart, or remove the paddock container."""
    flags = {
        "--build": build,
        "--remove": remove,
        "--start": start,
        "--stop": stop,
        "--restart": restart,
    }
    chosen = [name for name, value in flags.items() if value]
    if len(chosen) > 1:
        _fail(f"only one of {', '.join(chosen)} may be given at a time")

    _check_dependencies()

    if build:
        _build()
        return

    if remove:
        try:
            container.remove()
        except container.DockerError as exc:
            _fail(str(exc))
        return

    if start:
        _start()
        return

    if stop:
        try:
            container.stop()
        except container.DockerError as exc:
            _fail(str(exc))
        return

    if restart:
        try:
            container.restart()
        except container.DockerError as exc:
            _fail(str(exc))
        return

    # Always run, even if already running: this is also how env var changes
    # in settings.yaml reach the container, via container.set_environment,
    # without restarting it and killing whatever's running inside.
    _start()
