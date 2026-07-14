from __future__ import annotations

from pathlib import Path

import pytest

from paddock.config import ConfigError, ca_certificate_paths, load_settings, resolve_environment


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "settings.yaml"
    path.write_text(body)
    return path


def test_string_value_used_directly(tmp_path: Path):
    path = _write(tmp_path, "environment:\n  GITLAB_PAT: secret\n")
    assert resolve_environment(load_settings(path)) == {"GITLAB_PAT": "secret"}


def test_command_value_resolved(tmp_path: Path):
    path = _write(tmp_path, "environment:\n  GITLAB_PAT:\n    command: echo hi\n")
    assert resolve_environment(load_settings(path)) == {"GITLAB_PAT": "hi"}


def test_command_nonzero_exit_aborts(tmp_path: Path):
    path = _write(tmp_path, "environment:\n  X:\n    command: exit 3\n")
    with pytest.raises(ConfigError):
        resolve_environment(load_settings(path))


def test_unknown_top_level_key_rejected(tmp_path: Path):
    path = _write(tmp_path, "enviroment:\n  X: y\n")
    with pytest.raises(ConfigError):
        load_settings(path)


def test_command_missing_key_rejected(tmp_path: Path):
    path = _write(tmp_path, "environment:\n  X:\n    cmd: echo hi\n")
    with pytest.raises(ConfigError):
        load_settings(path)


def test_missing_file_is_empty_environment(tmp_path: Path):
    assert resolve_environment(load_settings(tmp_path / "does-not-exist.yaml")) == {}


def test_invalid_yaml_rejected(tmp_path: Path):
    path = _write(tmp_path, "environment: [\n")
    with pytest.raises(ConfigError):
        load_settings(path)


def test_non_hash_top_level_rejected(tmp_path: Path):
    path = _write(tmp_path, "- just\n- a\n- list\n")
    with pytest.raises(ConfigError):
        load_settings(path)


def test_ca_certificate_paths_expands_and_resolves(tmp_path: Path):
    cert = tmp_path / "corp-ca.pem"
    cert.write_text("fake cert contents")
    path = _write(tmp_path, f"ca_certificates:\n  - {cert}\n")
    assert ca_certificate_paths(load_settings(path)) == [cert]


def test_ca_certificate_paths_expands_tilde(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cert = tmp_path / "corp-ca.pem"
    cert.write_text("fake cert contents")
    path = _write(tmp_path, "ca_certificates:\n  - ~/corp-ca.pem\n")
    assert ca_certificate_paths(load_settings(path)) == [cert]


def test_ca_certificate_paths_missing_file_rejected(tmp_path: Path):
    path = _write(tmp_path, "ca_certificates:\n  - /nonexistent/corp-ca.pem\n")
    with pytest.raises(ConfigError):
        ca_certificate_paths(load_settings(path))


def test_absent_ca_certificates_is_empty(tmp_path: Path):
    path = _write(tmp_path, "environment: {}\n")
    assert ca_certificate_paths(load_settings(path)) == []
