"""Assembles and runs the ``docker compose`` invocation.

Two pure functions do the interesting work — building the argv and building
the interpolation environment — so they're testable without a docker daemon.
``exec_`` then hands the process over to the ``docker compose`` CLI.

On ``--env-file``: compose's ``--env-file`` feeds *interpolation* only, i.e.
the ``${VAR:-default}`` substitutions inside the compose file itself (like
``PADDOCK_SSH_PORT``). It is not a way to inject arbitrary environment
variables into the container — container environment belongs in the compose
file's ``environment:``/``env_file:`` keys instead.
"""

from __future__ import annotations

import os
import time
from typing import NoReturn

from . import paths


class ComposeError(Exception):
    """Raised when the docker compose CLI is missing."""


def compose_args(subcommand_args: list[str]) -> list[str]:
    """Build the full ``docker compose`` argv.

    Order matters: the packaged base file comes first so its directory
    establishes the compose project directory, then the per-machine override
    (if present) so its values win, then an ``--env-file`` (if present) for
    interpolation, then the caller's subcommand and its own arguments.
    """
    args = ["docker", "compose", "-f", str(paths.compose_file())]
    if paths.override_file().exists():
        args += ["-f", str(paths.override_file())]
    if paths.env_file().exists():
        args += ["--env-file", str(paths.env_file())]
    args += subcommand_args
    return args


def interpolation_env(refresh_tools: bool) -> dict[str, str]:
    """Build the child environment for the compose invocation.

    Starts from ``os.environ`` so the compose file's valueless pass-through
    entries (``GITHUB_TOKEN`` and friends) still pick up the user's shell,
    then layers on the ``PADDOCK_*`` interpolation variables. Never overwrites
    a variable the user already set, except ``PADDOCK_TOOLS_REFRESH`` when
    ``refresh_tools`` is true, which is the whole point of that flag.
    ``PADDOCK_SSH_PORT``/``PADDOCK_HTTP_PORT`` are pass-through only; paddock
    itself never sets them.
    """
    env = dict(os.environ)
    env["PADDOCK_AUTHORIZED_KEYS"] = str(paths.authorized_keys_path())

    certs_dir = paths.certs_dir()
    if certs_dir.is_dir() and any(certs_dir.glob("*.crt")):
        env["PADDOCK_CA_CONTEXT"] = str(certs_dir)

    if refresh_tools:
        env["PADDOCK_TOOLS_REFRESH"] = str(int(time.time()))

    return env


def exec_(args: list[str], env: dict[str, str]) -> NoReturn:
    """Replace the current process with the compose command.

    Every paddock invocation is a passthrough, so paddock never has work left
    once the child starts: signals and the terminal go straight to it, and
    compose's own exit code and error messages reach the user unmediated
    rather than being re-reported behind a second paddock-level error.
    """
    try:
        os.execvpe(args[0], args, env)
    except FileNotFoundError as exc:
        raise ComposeError("docker executable not found on PATH") from exc
