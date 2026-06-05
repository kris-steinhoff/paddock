"""Thin subprocess wrappers around the docker CLI.

List-form invocations (no shell), so environment values pass through safely.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class DockerError(Exception):
    """Raised when a docker command fails."""


def build(image: str, context_dir: Path) -> None:
    _run(["docker", "build", "-t", image, str(context_dir)])


def run(image: str, env: dict[str, str]) -> None:
    args = ["docker", "run", "-it", "--rm"]
    for name, value in env.items():
        args += ["-e", f"{name}={value}"]
    args.append(image)
    _run(args)


def image_exists(image: str) -> bool:
    completed = subprocess.run(
        ["docker", "image", "inspect", image],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


def remove(image: str) -> None:
    _run(["docker", "rmi", image])


def _run(args: list[str]) -> None:
    try:
        subprocess.run(args, check=True)
    except FileNotFoundError as exc:
        raise DockerError("docker executable not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise DockerError(
            f"docker command failed (exit {exc.returncode}): {' '.join(args)}"
        ) from exc
