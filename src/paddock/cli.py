"""The paddock CLI: build, run, and remove a per-repo container."""

from __future__ import annotations

from typing import NoReturn

import typer

from . import config, docker
from .resolver import RepoError, RepoTarget, resolve

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)

RepoArg = typer.Argument(..., metavar="REPO", help="Full repo path, e.g. github.com/org/name")


def _resolve(repo: str) -> RepoTarget:
    try:
        return resolve(repo)
    except RepoError as exc:
        _fail(str(exc))


def _fail(message: str) -> NoReturn:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


@app.command()
def build(repo: str = RepoArg) -> None:
    """Build the image from the repo's Dockerfile."""
    target = _resolve(repo)
    _build(target)


@app.command()
def run(
    repo: str = RepoArg,
    build: bool = typer.Option(False, "--build", help="Build the image before running."),
) -> None:
    """Run the image, injecting configured environment variables."""
    target = _resolve(repo)
    if build:
        _build(target)
    elif not docker.image_exists(target.image):
        _fail(f"image {target.image} not built yet; pass --build or run `paddock build {repo}`")

    try:
        settings = config.load_merged(target.settings_paths)
        env = config.resolve_environment(settings)
    except config.ConfigError as exc:
        _fail(str(exc))

    try:
        docker.run(target.image, env)
    except docker.DockerError as exc:
        _fail(str(exc))


@app.command()
def remove(repo: str = RepoArg) -> None:
    """Remove the built image."""
    target = _resolve(repo)
    try:
        docker.remove(target.image)
    except docker.DockerError as exc:
        _fail(str(exc))


def _build(target: RepoTarget) -> None:
    if not target.dockerfile.is_file():
        _fail(f"no Dockerfile at {target.dockerfile}")
    try:
        docker.build(target.image, target.leaf_dir)
    except docker.DockerError as exc:
        _fail(str(exc))
