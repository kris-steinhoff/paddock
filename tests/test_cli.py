from __future__ import annotations

import sys
from pathlib import Path

import pytest
from click.testing import Result
from typer.testing import CliRunner

from paddock import cli, compose, paths

runner = CliRunner()


def invoke(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> Result:
    """Invoke the app with ``sys.argv`` set to match.

    ``cli._passthrough_args`` reads ``sys.argv`` to tell whether a ``--``
    separator was typed, since Click consumes it without recording it.
    """
    monkeypatch.setattr(sys, "argv", ["paddock", *argv])
    return runner.invoke(cli.app, argv)


@pytest.fixture
def fake_compose(monkeypatch: pytest.MonkeyPatch):
    """Capture the argv/env that would go to docker compose instead of execing it."""
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_exec(args: list[str], env: dict[str, str]) -> None:
        calls.append((args, env))

    monkeypatch.setattr(compose, "exec_", fake_exec)
    return calls


# --- _passthrough_args, the pure separator check -----------------------------


def test_passthrough_args_returns_none_without_separator():
    assert cli._passthrough_args(["up", "-d"]) is None


def test_passthrough_args_returns_args_after_separator():
    assert cli._passthrough_args(["--", "up", "-d"]) == ["up", "-d"]


def test_passthrough_args_returns_empty_list_for_bare_separator():
    assert cli._passthrough_args(["--"]) == []


def test_passthrough_args_splits_on_the_first_separator_only():
    assert cli._passthrough_args(["--init", "--", "exec", "agent", "--", "zsh"]) == [
        "exec",
        "agent",
        "--",
        "zsh",
    ]


# --- top-level behavior ------------------------------------------------------


def test_bare_invocation_prints_help_and_exits_zero(monkeypatch: pytest.MonkeyPatch):
    result = invoke([], monkeypatch)
    assert result.exit_code == 0
    assert "Usage:" in result.output


def test_bare_separator_prints_help_and_exits_zero(monkeypatch: pytest.MonkeyPatch):
    result = invoke(["--"], monkeypatch)
    assert result.exit_code == 0
    assert "Usage:" in result.output


def test_help_advertises_passthrough_args(monkeypatch: pytest.MonkeyPatch):
    result = invoke(["--help"], monkeypatch)
    assert result.exit_code == 0
    assert "ARGS" in result.output
    for flag in ["--init", "--refresh", "--no-refresh"]:
        assert flag in result.output


def test_version(monkeypatch: pytest.MonkeyPatch):
    result = invoke(["--version"], monkeypatch)
    assert result.exit_code == 0
    assert result.output.strip()


# --- the separator is required -----------------------------------------------


def test_args_without_separator_fail(fake_compose, xdg_base: Path, monkeypatch):
    result = invoke(["start"], monkeypatch)

    assert result.exit_code == 1
    assert "must follow '--'" in result.output
    assert fake_compose == []


def test_args_without_separator_fail_even_with_flags(fake_compose, xdg_base: Path, monkeypatch):
    result = invoke(["--no-refresh", "logs", "-f"], monkeypatch)

    assert result.exit_code == 1
    assert fake_compose == []


# --- passthrough -------------------------------------------------------------


def test_passthrough_execs_compose(fake_compose, xdg_base: Path, monkeypatch):
    invoke(["--", "start"], monkeypatch)

    args, _ = fake_compose[0]
    assert args[:3] == ["docker", "compose", "-f"]
    assert args[-1] == "start"


def test_passthrough_forwards_flags_untouched(fake_compose, xdg_base: Path, monkeypatch):
    invoke(["--", "logs", "-f"], monkeypatch)

    args, _ = fake_compose[0]
    assert args[-2:] == ["logs", "-f"]


def test_passthrough_forwards_multiple_args(fake_compose, xdg_base: Path, monkeypatch):
    invoke(["--", "exec", "agent", "zsh"], monkeypatch)

    args, _ = fake_compose[0]
    assert args[-3:] == ["exec", "agent", "zsh"]


def test_passthrough_forwards_compose_help(fake_compose, xdg_base: Path, monkeypatch):
    invoke(["--", "--help"], monkeypatch)

    args, _ = fake_compose[0]
    assert args[-1] == "--help"


def test_compose_error_prints_error_and_exits_one(xdg_base: Path, monkeypatch: pytest.MonkeyPatch):
    def raise_error(args: list[str], env: dict[str, str]) -> None:
        raise compose.ComposeError("docker executable not found on PATH")

    monkeypatch.setattr(compose, "exec_", raise_error)

    result = invoke(["--", "up"], monkeypatch)

    assert result.exit_code == 1
    assert "error: docker executable not found on PATH" in result.output


# --- --refresh / --no-refresh ------------------------------------------------


def test_refresh_is_the_default(fake_compose, xdg_base: Path, monkeypatch):
    invoke(["--", "build"], monkeypatch)

    _, env = fake_compose[0]
    assert env["PADDOCK_TOOLS_REFRESH"].isdigit()


def test_no_refresh_leaves_tools_refresh_unset(fake_compose, xdg_base: Path, monkeypatch):
    invoke(["--no-refresh", "--", "build"], monkeypatch)

    _, env = fake_compose[0]
    assert "PADDOCK_TOOLS_REFRESH" not in env


# --- the authorized_keys warning ---------------------------------------------


def test_warns_when_authorized_keys_missing(fake_compose, xdg_base: Path, monkeypatch):
    result = invoke(["--", "up"], monkeypatch)

    assert "warning:" in result.output
    assert "authorized_keys" in result.output


def test_no_warning_when_authorized_keys_present(fake_compose, xdg_base: Path, monkeypatch):
    paths.config_dir().mkdir(parents=True)
    paths.authorized_keys_path().write_text("ssh-ed25519 AAAA... test\n")

    result = invoke(["--", "up"], monkeypatch)

    assert "warning:" not in result.output


# --- --init ------------------------------------------------------------------


def test_init_creates_config_and_certs_dirs(xdg_base: Path, monkeypatch: pytest.MonkeyPatch):
    result = invoke(["--init"], monkeypatch)

    assert result.exit_code == 0
    assert paths.config_dir().is_dir()
    assert paths.certs_dir().is_dir()


def test_init_alone_does_not_print_help(xdg_base: Path, monkeypatch: pytest.MonkeyPatch):
    result = invoke(["--init"], monkeypatch)
    assert "Usage:" not in result.output


def test_init_prompts_for_authorized_keys_when_missing(
    xdg_base: Path, monkeypatch: pytest.MonkeyPatch
):
    result = invoke(["--init"], monkeypatch)
    assert "authorized_keys" in result.output


def test_init_does_not_prompt_when_authorized_keys_present(
    xdg_base: Path, monkeypatch: pytest.MonkeyPatch
):
    paths.config_dir().mkdir(parents=True)
    paths.authorized_keys_path().write_text("ssh-ed25519 AAAA... test\n")

    result = invoke(["--init"], monkeypatch)

    assert "authorized_keys" not in result.output


def test_init_is_idempotent(xdg_base: Path, monkeypatch: pytest.MonkeyPatch):
    invoke(["--init"], monkeypatch)
    result = invoke(["--init"], monkeypatch)

    assert result.exit_code == 0
    assert "already exists" in result.output


def test_init_then_passthrough_runs_both(fake_compose, xdg_base: Path, monkeypatch):
    result = invoke(["--init", "--", "up"], monkeypatch)

    assert result.exit_code == 0
    assert paths.config_dir().is_dir()
    args, _ = fake_compose[0]
    assert args[-1] == "up"
