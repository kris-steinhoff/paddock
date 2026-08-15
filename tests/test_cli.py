from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from paddock import cli, compose, paths

runner = CliRunner()


@pytest.fixture
def fake_compose(monkeypatch: pytest.MonkeyPatch):
    """Capture the argv/env that would go to docker compose instead of running it."""
    calls: list[tuple[str, list[str], dict[str, str]]] = []

    def fake_run(args: list[str], env: dict[str, str]) -> None:
        calls.append(("run", args, env))

    def fake_exec(args: list[str], env: dict[str, str]) -> None:
        calls.append(("exec", args, env))

    monkeypatch.setattr(compose, "run", fake_run)
    monkeypatch.setattr(compose, "exec_", fake_exec)
    return calls


def test_bare_invocation_prints_help_and_exits_zero():
    result = runner.invoke(cli.app, [])
    assert result.exit_code == 0
    assert "Usage:" in result.output


def test_help_lists_every_subcommand():
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    for name in [
        "init",
        "build",
        "up",
        "down",
        "start",
        "stop",
        "restart",
        "status",
        "logs",
        "compose",
    ]:
        assert name in result.output


def test_version():
    result = runner.invoke(cli.app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip()


def test_init_creates_config_and_certs_dirs(xdg_base: Path):
    result = runner.invoke(cli.app, ["init"])

    assert result.exit_code == 0
    assert paths.config_dir().is_dir()
    assert paths.certs_dir().is_dir()


def test_init_prompts_for_authorized_keys_when_missing(xdg_base: Path):
    result = runner.invoke(cli.app, ["init"])
    assert "authorized_keys" in result.output


def test_init_does_not_prompt_when_authorized_keys_present(xdg_base: Path):
    paths.config_dir().mkdir(parents=True)
    paths.authorized_keys_path().write_text("ssh-ed25519 AAAA... test\n")

    result = runner.invoke(cli.app, ["init"])

    assert "authorized_keys" not in result.output


def test_init_is_idempotent(xdg_base: Path):
    runner.invoke(cli.app, ["init"])
    result = runner.invoke(cli.app, ["init"])

    assert result.exit_code == 0
    assert "already exists" in result.output


def test_build_refreshes_tools_by_default(fake_compose, xdg_base: Path):
    result = runner.invoke(cli.app, ["build"])
    assert result.exit_code == 0
    kind, args, env = fake_compose[0]
    assert kind == "run"
    assert args[-1] == "build"
    assert "PADDOCK_TOOLS_REFRESH" in env


def test_build_cached_pins_tools_refresh(fake_compose, xdg_base: Path):
    runner.invoke(cli.app, ["build", "--cached"])
    _, _, env = fake_compose[0]
    assert "PADDOCK_TOOLS_REFRESH" not in env


def test_build_no_cache_passes_through(fake_compose, xdg_base: Path):
    runner.invoke(cli.app, ["build", "--no-cache"])
    _, args, _ = fake_compose[0]
    assert args[-2:] == ["build", "--no-cache"]


def test_up_defaults_to_no_build(fake_compose, xdg_base: Path):
    runner.invoke(cli.app, ["up"])
    _, args, env = fake_compose[0]
    assert args[-2:] == ["up", "-d"]
    assert "PADDOCK_TOOLS_REFRESH" not in env


def test_up_build_refreshes_tools(fake_compose, xdg_base: Path):
    runner.invoke(cli.app, ["up", "--build"])
    _, args, env = fake_compose[0]
    assert args[-3:] == ["up", "-d", "--build"]
    assert "PADDOCK_TOOLS_REFRESH" in env


def test_up_build_cached_stays_cached(fake_compose, xdg_base: Path):
    runner.invoke(cli.app, ["up", "--build", "--cached"])
    _, args, env = fake_compose[0]
    assert "--build" in args
    assert "PADDOCK_TOOLS_REFRESH" not in env


def test_down_defaults_to_no_volumes(fake_compose, xdg_base: Path):
    runner.invoke(cli.app, ["down"])
    _, args, _ = fake_compose[0]
    assert "-v" not in args


def test_down_volumes_forwards_v(fake_compose, xdg_base: Path):
    runner.invoke(cli.app, ["down", "--volumes"])
    _, args, _ = fake_compose[0]
    assert args[-1] == "-v"


@pytest.mark.parametrize("name", ["start", "stop", "restart"])
def test_lifecycle_commands_map_to_compose_subcommand(fake_compose, xdg_base: Path, name: str):
    runner.invoke(cli.app, [name])
    _, args, _ = fake_compose[0]
    assert args[-1] == name


def test_status_reports_default_ssh_port(fake_compose, xdg_base: Path):
    result = runner.invoke(cli.app, ["status"])
    assert "2222" in result.output
    _, args, _ = fake_compose[0]
    assert args[-1] == "ps"


def test_status_reports_ssh_port_from_env_file(fake_compose, xdg_base: Path):
    paths.config_dir().mkdir(parents=True)
    paths.env_file().write_text("PADDOCK_SSH_PORT=2299\n")

    result = runner.invoke(cli.app, ["status"])

    assert "2299" in result.output


def test_status_reports_ssh_port_from_shell_env(
    fake_compose, xdg_base: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("PADDOCK_SSH_PORT", "9999")
    result = runner.invoke(cli.app, ["status"])
    assert "9999" in result.output


def test_logs_execs_compose(fake_compose, xdg_base: Path):
    runner.invoke(cli.app, ["logs"])
    kind, args, _ = fake_compose[0]
    assert kind == "exec"
    assert args[-1] == "logs"


def test_logs_follow_forwards_flag(fake_compose, xdg_base: Path):
    runner.invoke(cli.app, ["logs", "-f"])
    _, args, _ = fake_compose[0]
    assert args[-2:] == ["logs", "-f"]


def test_compose_passthrough_execs_with_trailing_args(fake_compose, xdg_base: Path):
    runner.invoke(cli.app, ["compose", "--", "config"])
    kind, args, _ = fake_compose[0]
    assert kind == "exec"
    assert args[-1] == "config"


def test_compose_passthrough_forwards_multiple_args(fake_compose, xdg_base: Path):
    runner.invoke(cli.app, ["compose", "--", "exec", "agent", "zsh"])
    _, args, _ = fake_compose[0]
    assert args[-3:] == ["exec", "agent", "zsh"]


@pytest.mark.parametrize("name", ["up", "start", "restart"])
def test_warns_when_authorized_keys_missing(fake_compose, xdg_base: Path, name: str):
    result = runner.invoke(cli.app, [name])
    assert "warning:" in result.output
    assert "authorized_keys" in result.output


@pytest.mark.parametrize("name", ["up", "start", "restart"])
def test_no_warning_when_authorized_keys_present(fake_compose, xdg_base: Path, name: str):
    paths.config_dir().mkdir(parents=True)
    paths.authorized_keys_path().write_text("ssh-ed25519 AAAA... test\n")

    result = runner.invoke(cli.app, [name])

    assert "warning:" not in result.output


def test_build_does_not_warn_about_authorized_keys(fake_compose, xdg_base: Path):
    result = runner.invoke(cli.app, ["build"])
    assert "warning:" not in result.output


def test_compose_error_prints_error_and_exits_one(monkeypatch: pytest.MonkeyPatch, xdg_base: Path):
    def raise_error(args: list[str], env: dict[str, str]) -> None:
        raise compose.ComposeError("docker executable not found on PATH")

    monkeypatch.setattr(compose, "run", raise_error)

    result = runner.invoke(cli.app, ["start"])

    assert result.exit_code == 1
    assert "error: docker executable not found on PATH" in result.output
