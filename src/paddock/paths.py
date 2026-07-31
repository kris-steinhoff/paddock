"""The config-dir layout and the packaged-image location.

paddock keeps no state directory of its own: docker owns all of it (images,
containers, volumes). These are path predicates only — existence checks and
error messages belong to callers (CLI/preflight).
"""

from __future__ import annotations

import os
from pathlib import Path

_IMAGE_DIR = Path(__file__).resolve().parent / "image"


def config_dir() -> Path:
    """Return ``${XDG_CONFIG_HOME:-~/.config}/paddock``."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "paddock"


def compose_file() -> Path:
    """Return the packaged base ``docker-compose.yml``."""
    return _IMAGE_DIR / "docker-compose.yml"


def override_file() -> Path:
    """Return the per-machine ``docker-compose.override.yml``."""
    return config_dir() / "docker-compose.override.yml"


def env_file() -> Path:
    """Return the compose interpolation ``.env`` file."""
    return config_dir() / ".env"


def authorized_keys_path() -> Path:
    """Return the ``authorized_keys`` file mounted into the container."""
    return config_dir() / "authorized_keys"


def certs_dir() -> Path:
    """Return the directory of CA certificates trusted by the image build."""
    return config_dir() / "certs"
