"""XDG config/state path helpers."""

from __future__ import annotations

import os
from pathlib import Path


def config_dir() -> Path:
    """Return ``${XDG_CONFIG_HOME:-~/.config}/paddock``."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "paddock"


def settings_path() -> Path:
    """Return the single settings file path."""
    return config_dir() / "settings.yaml"


def state_dir() -> Path:
    """Return ``${XDG_STATE_HOME:-~/.local/state}/paddock``."""
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / "paddock"


def ssh_home_dir() -> Path:
    """Return the isolated ``$HOME`` used for the herdr attach subprocess."""
    return state_dir() / "ssh_home"
