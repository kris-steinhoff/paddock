"""Paddock's own dedicated keypair, isolated ssh home, and the herdr attach.

Attaching runs ``herdr --remote ssh://agent@localhost:<port>`` with ``HOME``
overridden to a paddock-private directory. herdr's managed-ssh-config feature
includes ``$HOME/.ssh/config`` when generating its per-attach ssh config, so
overriding ``HOME`` for just this subprocess call gives paddock its own ssh
config/known_hosts/identity file without ever touching the user's real
``~/.ssh``.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import NoReturn

from . import paths


class SshError(Exception):
    """Raised when the keypair cannot be generated."""


def private_key_path() -> Path:
    return paths.ssh_home_dir() / ".ssh" / "id_ed25519"


def public_key_path() -> Path:
    return private_key_path().with_suffix(".pub")


def known_hosts_path() -> Path:
    return paths.ssh_home_dir() / ".ssh" / "known_hosts"


def ensure_keypair() -> Path:
    """Generate paddock's dedicated ed25519 keypair if it doesn't exist yet.

    Returns the public key path (what gets mounted as the container's
    authorized_keys).
    """
    private_key = private_key_path()
    ssh_dir = private_key.parent
    ssh_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(ssh_dir, 0o700)

    if not private_key.is_file():
        try:
            subprocess.run(
                [
                    "ssh-keygen",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-f",
                    str(private_key),
                    "-C",
                    "paddock",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise SshError("ssh-keygen executable not found on PATH") from exc
        except subprocess.CalledProcessError as exc:
            raise SshError(f"ssh-keygen failed: {exc.stderr.strip()}") from exc
        os.chmod(private_key, 0o600)

    return public_key_path()


def ensure_ssh_home() -> Path:
    """Write paddock's isolated ssh config, idempotently. Returns the ssh home dir.

    ssh's own tilde-expansion for values inside a config file resolves against
    the real passwd-database home directory, not the ``HOME`` env var override
    used for the herdr subprocess — so paths here must be absolute, not ``~/...``,
    or they'd silently resolve against the user's real home instead of this one.
    """
    ssh_home = paths.ssh_home_dir()
    ssh_dir = ssh_home / ".ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(ssh_dir, 0o700)
    config = (
        "Host *\n"
        f'    IdentityFile "{private_key_path()}"\n'
        "    IdentitiesOnly yes\n"
        f'    UserKnownHostsFile "{known_hosts_path()}"\n'
        "    ForwardAgent yes\n"
        "    StrictHostKeyChecking accept-new\n"
    )
    (ssh_dir / "config").write_text(config)
    return ssh_home


def _real_herdr_config_path() -> Path:
    configured = os.environ.get("HERDR_CONFIG_PATH")
    if configured:
        return Path(configured)
    return Path.home() / ".config" / "herdr" / "config.toml"


def attach(port: int) -> NoReturn:
    """Exec into ``herdr --remote`` against the container, replacing this process."""
    ssh_home = ensure_ssh_home()
    herdr_config = _real_herdr_config_path()

    env = dict(os.environ)
    env["HOME"] = str(ssh_home)
    env["HERDR_CONFIG_PATH"] = str(herdr_config)

    os.execvpe("herdr", ["herdr", "--remote", f"ssh://agent@localhost:{port}"], env)
