"""Thin subprocess wrappers around the docker CLI, owning the one paddock container.

List-form invocations (no shell), so environment values pass through safely.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

IMAGE = "paddock"
CONTAINER = "paddock"
HOME_VOLUME = "paddock_home"
SSH_HOST_KEYS_VOLUME = "paddock_ssh_host_keys"
PORT = 2223

IMAGE_DIR = Path(__file__).resolve().parent / "image"


class DockerError(Exception):
    """Raised when a docker command fails."""


def build(ca_certificates: list[Path] | None = None) -> None:
    """Build the image, assembling a build context that includes any configured
    CA certificates alongside the packaged Dockerfile/entrypoint/sshd_config.
    """
    with tempfile.TemporaryDirectory(prefix="paddock-build-") as tmp_str:
        context_dir = Path(tmp_str)
        shutil.copytree(IMAGE_DIR, context_dir, dirs_exist_ok=True)
        certs_dir = context_dir / "ca-certificates"
        certs_dir.mkdir(exist_ok=True)
        for cert in ca_certificates or []:
            shutil.copyfile(cert, certs_dir / f"{cert.stem}.crt")
        _run(["docker", "build", "-t", IMAGE, str(context_dir)])


def image_exists() -> bool:
    return _check(["docker", "image", "inspect", IMAGE])


def container_exists() -> bool:
    return _check(["docker", "container", "inspect", CONTAINER])


def container_running() -> bool:
    completed = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER],
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0 and completed.stdout.strip() == "true"


def start(env: dict[str, str], authorized_keys: Path) -> None:
    """Create and start the container if it doesn't exist yet, else start it."""
    if container_exists():
        if not container_running():
            _run(["docker", "start", CONTAINER])
        return

    args = [
        "docker",
        "run",
        "-d",
        "--name",
        CONTAINER,
        "-p",
        f"{PORT}:22",
        "-v",
        f"{HOME_VOLUME}:/home/agent",
        "-v",
        f"{SSH_HOST_KEYS_VOLUME}:/etc/ssh",
        "-v",
        f"{authorized_keys}:/run/paddock/authorized_keys:ro",
        "--add-host",
        "host.docker.internal:host-gateway",
        "--restart",
        "unless-stopped",
    ]
    for name, value in env.items():
        args += ["-e", f"{name}={value}"]
    args.append(IMAGE)
    _run(args)


def stop() -> None:
    _run(["docker", "stop", CONTAINER])


def restart() -> None:
    _run(["docker", "restart", CONTAINER])


def remove() -> None:
    if container_exists():
        if container_running():
            _run(["docker", "stop", CONTAINER])
        _run(["docker", "rm", CONTAINER])
    if image_exists():
        _run(["docker", "rmi", IMAGE])


def _check(args: list[str]) -> bool:
    completed = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return completed.returncode == 0


def _run(args: list[str]) -> None:
    try:
        subprocess.run(args, check=True)
    except FileNotFoundError as exc:
        raise DockerError("docker executable not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise DockerError(
            f"docker command failed (exit {exc.returncode}): {' '.join(args)}"
        ) from exc
