from __future__ import annotations

import stat
from pathlib import Path

from paddock import ssh


def test_ensure_keypair_generates_files(xdg_base: Path):
    public_key = ssh.ensure_keypair()

    assert public_key == ssh.public_key_path()
    assert ssh.private_key_path().is_file()
    assert public_key.is_file()
    assert stat.S_IMODE(ssh.private_key_path().stat().st_mode) == 0o600


def test_ensure_keypair_idempotent(xdg_base: Path):
    ssh.ensure_keypair()
    first = ssh.private_key_path().read_text()
    ssh.ensure_keypair()
    assert ssh.private_key_path().read_text() == first


def test_ensure_ssh_home_writes_config(xdg_base: Path):
    ssh_home = ssh.ensure_ssh_home()

    config_path = ssh_home / ".ssh" / "config"
    assert config_path.is_file()
    body = config_path.read_text()
    assert "ForwardAgent yes" in body
    assert "StrictHostKeyChecking accept-new" in body
    assert "IdentitiesOnly yes" in body
    assert str(ssh.private_key_path()) in body
    assert str(ssh.known_hosts_path()) in body
    assert "~" not in body
    assert stat.S_IMODE((ssh_home / ".ssh").stat().st_mode) == 0o700
