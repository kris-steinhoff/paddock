from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def xdg_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point XDG_CONFIG_HOME/XDG_STATE_HOME at a temp dir and return the paddock base."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return tmp_path
