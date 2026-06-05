from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def xdg_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point XDG_CONFIG_HOME at a temp dir and return the paddock base."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path / "paddock"


def write_settings(base: Path, rel: str, body: str) -> Path:
    """Write a settings.yaml at ``repos/<rel>`` under the paddock base."""
    path = base / "repos" / rel / "settings.yaml" if rel else base / "repos" / "settings.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path
