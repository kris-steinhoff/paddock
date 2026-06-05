from __future__ import annotations

from pathlib import Path

import pytest

from paddock.config import (
    ConfigError,
    load_merged,
    named_volumes,
    resolve_environment,
    volume_args,
)


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body)
    return path


def test_merge_precedence_most_specific_wins(tmp_path: Path):
    global_ = _write(tmp_path, "global.yaml", "environment:\n  GITLAB_PAT: global\n  KEEP: g\n")
    provider = _write(tmp_path, "provider.yaml", "environment:\n  GITLAB_PAT: provider\n")
    org = _write(tmp_path, "org.yaml", "environment:\n  GITLAB_PAT: org\n")

    settings = load_merged([global_, provider, org])
    env = resolve_environment(settings)
    assert env == {"GITLAB_PAT": "org", "KEEP": "g"}


def test_string_value_used_directly(tmp_path: Path):
    path = _write(tmp_path, "s.yaml", "environment:\n  GITLAB_PAT: secret\n")
    assert resolve_environment(load_merged([path])) == {"GITLAB_PAT": "secret"}


def test_command_value_resolved(tmp_path: Path):
    path = _write(tmp_path, "c.yaml", "environment:\n  GITLAB_PAT:\n    command: echo hi\n")
    assert resolve_environment(load_merged([path])) == {"GITLAB_PAT": "hi"}


def test_command_nonzero_exit_aborts(tmp_path: Path):
    path = _write(tmp_path, "c.yaml", "environment:\n  X:\n    command: exit 3\n")
    with pytest.raises(ConfigError):
        resolve_environment(load_merged([path]))


def test_unknown_top_level_key_rejected(tmp_path: Path):
    path = _write(tmp_path, "bad.yaml", "enviroment:\n  X: y\n")
    with pytest.raises(ConfigError):
        load_merged([path])


def test_command_missing_key_rejected(tmp_path: Path):
    path = _write(tmp_path, "bad.yaml", "environment:\n  X:\n    cmd: echo hi\n")
    with pytest.raises(ConfigError):
        load_merged([path])


def test_empty_settings_list_is_empty_environment():
    assert resolve_environment(load_merged([])) == {}


def test_volume_args_returns_raw_strings(tmp_path: Path):
    path = _write(
        tmp_path,
        "v.yaml",
        "volumes:\n  cache: paddock-cache:/home/dev/.cache\n  src: /home/me/src:/workspace:ro\n",
    )
    assert volume_args(load_merged([path])) == [
        "paddock-cache:/home/dev/.cache",
        "/home/me/src:/workspace:ro",
    ]


def test_named_volumes_excludes_bind_mounts(tmp_path: Path):
    path = _write(
        tmp_path,
        "v.yaml",
        "volumes:\n"
        "  named: paddock-cache:/home/dev/.cache\n"
        "  abs: /home/me/src:/workspace\n"
        "  rel: ./data:/data\n"
        "  home: ~/state:/state\n",
    )
    assert named_volumes(load_merged([path])) == ["paddock-cache"]


def test_volumes_merge_precedence_most_specific_wins(tmp_path: Path):
    base = _write(tmp_path, "base.yaml", "volumes:\n  cache: old:/c\n  keep: keep:/k\n")
    override = _write(tmp_path, "override.yaml", "volumes:\n  cache: new:/c\n")

    settings = load_merged([base, override])
    assert settings.volumes == {"cache": "new:/c", "keep": "keep:/k"}


def test_non_string_volume_value_rejected(tmp_path: Path):
    path = _write(tmp_path, "bad.yaml", "volumes:\n  cache:\n    name: paddock-cache\n")
    with pytest.raises(ConfigError):
        load_merged([path])


def test_absent_volumes_is_empty():
    settings = load_merged([])
    assert volume_args(settings) == []
    assert named_volumes(settings) == []
