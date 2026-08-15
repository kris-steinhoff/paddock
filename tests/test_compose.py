from __future__ import annotations

from pathlib import Path

import pytest

from paddock import compose, paths


def test_compose_args_without_override_or_env_file(xdg_base: Path):
    args = compose.compose_args(["up", "-d"])
    assert args == ["docker", "compose", "-f", str(paths.compose_file()), "up", "-d"]


def test_compose_args_includes_override_when_present(xdg_base: Path):
    paths.config_dir().mkdir(parents=True)
    paths.override_file().write_text("services: {}\n")

    args = compose.compose_args(["up", "-d"])

    assert args == [
        "docker",
        "compose",
        "-f",
        str(paths.compose_file()),
        "-f",
        str(paths.override_file()),
        "up",
        "-d",
    ]


def test_compose_args_includes_env_file_when_present(xdg_base: Path):
    paths.config_dir().mkdir(parents=True)
    paths.env_file().write_text("PADDOCK_SSH_PORT=2224\n")

    args = compose.compose_args(["up", "-d"])

    assert args == [
        "docker",
        "compose",
        "-f",
        str(paths.compose_file()),
        "--env-file",
        str(paths.env_file()),
        "up",
        "-d",
    ]


def test_compose_args_orders_base_before_override_before_env_file(xdg_base: Path):
    paths.config_dir().mkdir(parents=True)
    paths.override_file().write_text("services: {}\n")
    paths.env_file().write_text("PADDOCK_SSH_PORT=2224\n")

    args = compose.compose_args(["up", "-d"])

    assert args == [
        "docker",
        "compose",
        "-f",
        str(paths.compose_file()),
        "-f",
        str(paths.override_file()),
        "--env-file",
        str(paths.env_file()),
        "up",
        "-d",
    ]


def test_interpolation_env_always_sets_authorized_keys(xdg_base: Path):
    env = compose.interpolation_env(refresh_tools=False)
    assert env["PADDOCK_AUTHORIZED_KEYS"] == str(paths.authorized_keys_path())


def test_interpolation_env_omits_ca_context_when_certs_dir_absent(xdg_base: Path):
    env = compose.interpolation_env(refresh_tools=False)
    assert "PADDOCK_CA_CONTEXT" not in env


def test_interpolation_env_omits_ca_context_when_certs_dir_has_no_crt(xdg_base: Path):
    paths.certs_dir().mkdir(parents=True)
    (paths.certs_dir() / "readme.txt").write_text("not a cert")

    env = compose.interpolation_env(refresh_tools=False)

    assert "PADDOCK_CA_CONTEXT" not in env


def test_interpolation_env_sets_ca_context_when_crt_present(xdg_base: Path):
    paths.certs_dir().mkdir(parents=True)
    (paths.certs_dir() / "corp.crt").write_text("fake cert")

    env = compose.interpolation_env(refresh_tools=False)

    assert env["PADDOCK_CA_CONTEXT"] == str(paths.certs_dir())


def test_interpolation_env_leaves_tools_refresh_unset_by_default(xdg_base: Path):
    env = compose.interpolation_env(refresh_tools=False)
    assert "PADDOCK_TOOLS_REFRESH" not in env


def test_interpolation_env_sets_tools_refresh_when_requested(xdg_base: Path):
    env = compose.interpolation_env(refresh_tools=True)
    assert env["PADDOCK_TOOLS_REFRESH"].isdigit()


def test_interpolation_env_never_overwrites_user_set_ssh_port(
    xdg_base: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("PADDOCK_SSH_PORT", "9999")
    env = compose.interpolation_env(refresh_tools=False)
    assert env["PADDOCK_SSH_PORT"] == "9999"


def test_interpolation_env_never_overwrites_user_set_tools_refresh_without_request(
    xdg_base: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("PADDOCK_TOOLS_REFRESH", "42")
    env = compose.interpolation_env(refresh_tools=False)
    assert env["PADDOCK_TOOLS_REFRESH"] == "42"


def test_exec_raises_compose_error_when_executable_missing():
    with pytest.raises(compose.ComposeError):
        compose.exec_(["paddock-does-not-exist-anywhere"], env={"PATH": ""})
