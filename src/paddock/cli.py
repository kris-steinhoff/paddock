"""The paddock CLI: build, start, stop, restart, and remove the agent container.

Uses herdr to attach to a general-purpose agent container.
"""

from __future__ import annotations

import shutil
from importlib.metadata import version as _pkg_version
from typing import NoReturn

import typer

from . import config, container, paths, ssh

app = typer.Typer(add_completion=False, help=__doc__)

REQUIRED_EXECUTABLES = ["docker", "herdr", "ssh-keygen"]


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
        return config.load_settings(paths.settings_path())
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
    try:
        authorized_keys = ssh.ensure_keypair()
    except ssh.SshError as exc:
        _fail(str(exc))
    settings = _load_settings()
    try:
        env = config.resolve_environment(settings)
    except config.ConfigError as exc:
        _fail(str(exc))
    try:
        container.start(env, authorized_keys)
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
    """Uses herdr to attach to a general-purpose agent container."""
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

    if not container.container_running():
        _start()
    ssh.attach(container.PORT)
