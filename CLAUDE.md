# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What paddock is

A uv-managed Python CLI that wraps a single general-purpose development
container (build/start/stop/restart/remove) and attaches to it with
[herdr](https://herdr.dev). One Dockerfile ships baked into the paddock
package itself — there's no per-repo image or config tree. See `README.md`
for user-facing usage and the config format.

## Commands

Everything runs through `uv`:

- `uv sync` — install deps and create `.venv`.
- `uv run paddock [--build|--start|--stop|--restart|--remove]` — invoke the CLI. Bare `paddock` builds/starts as needed and attaches via herdr.
- `uv run ruff format .` — format. `uv run ruff check .` — lint.
- `uv run ty check` — type check.
- `uv run pytest` — run all tests. Single test: `uv run pytest tests/test_config.py::test_command_value_resolved`.

Requires Python >= 3.13. `ruff`, `ty`, and `pytest` are dev dependencies (run them via `uv run`, not `uvx`). `docker`, `herdr`, and `ssh-keygen` must be on `PATH` at runtime (checked up front in `cli.py`).

## Architecture

- `paths.py` — XDG config/state path helpers: `settings_path()` (the one config file) and `ssh_home_dir()` (paddock's isolated `$HOME` for the herdr attach).
- `config.py` — pydantic models plus single-file load and env resolution. `load_settings` reads one optional `settings.yaml` (missing file = empty settings) and validates with `extra="forbid"`. `resolve_environment` turns each value into a string: a literal is used as-is, a `{command: ...}` is run via `sh -c` with stdout's trailing newline stripped. `ca_certificate_paths` expands (`~`) and validates each `ca_certificates` entry exists, raising `ConfigError` early rather than failing deep inside a docker build.
- `container.py` — thin list-form `subprocess` wrappers (no shell) around `docker build/run/start/stop/restart/rm/rmi`, scoped to the one fixed `paddock` image/container name. `IMAGE_DIR` resolves to the `image/` directory baked into the installed package (Dockerfile, entrypoint.sh, sshd_config — adapted from `../agent-container`). `build()` assembles a fresh temp build context per call (copies `IMAGE_DIR` plus a `ca-certificates/` dir populated from any configured CA paths) rather than building `IMAGE_DIR` directly, since the installed package directory shouldn't be mutated and CA cert paths live outside it. `set_environment()` writes resolved `environment:` values into `~/.ssh/environment` inside the container via `docker exec` (piped over stdin, not baked in at `docker run -e` time) — sshd (`PermitUserEnvironment yes` in `sshd_config`) reads that file fresh per new session, so edited `settings.yaml` values reach the container on the next shell/herdr session without restarting or recreating it, which would kill anything already running inside. `cli.py`'s default (no-flag) path calls `_start()` unconditionally, even when already running, specifically so this refresh happens on every plain `paddock` invocation. **Gotcha**: `/etc/ssh` is the `paddock_ssh_host_keys` volume (so host keys survive container recreation), and Docker only seeds a named volume from the image on its *first* use — a config file placed directly under `/etc/ssh` by the Dockerfile (e.g. `sshd_config.d/paddock.conf`) would silently never be updated by a later image rebuild once that volume already exists, since the volume's stale content always wins. So `sshd_config` is baked into the image at `/etc/paddock/sshd_config` (outside `/etc/ssh`) and `entrypoint.sh` copies it into `/etc/ssh/sshd_config.d/paddock.conf` on every container start, the same pattern already used there for `authorized_keys`.
- `ssh.py` — generates paddock's own dedicated ed25519 keypair (`ensure_keypair`, under `ssh_home_dir()`), writes an isolated ssh config (`ensure_ssh_home`), and execs into `herdr --remote ssh://agent@localhost:<port>` (`attach`) with `HOME` overridden to that same directory for just that subprocess call. herdr's managed-ssh-config feature includes `$HOME/.ssh/config` when building its per-attach config, so this scopes ssh config/known_hosts/identity resolution to paddock's own directory instead of the user's real `~/.ssh`, with no `Host` alias needed anywhere since the port/user are embedded directly in the `ssh://` URI. **Gotcha**: ssh's own tilde-expansion for values *inside* a config file (e.g. `IdentityFile ~/...`) resolves against the real passwd-database home directory, not the `HOME` env var override — only herdr's own `Include "$HOME/.ssh/config"` line (which it constructs as a literal path string itself) respects the override. So `ensure_ssh_home` writes `IdentityFile`/`UserKnownHostsFile` as absolute paths, never `~`, or they'd silently resolve against the user's real `~/.ssh`. The config also sets `IdentitiesOnly yes` — without it, a forwarded ssh-agent offering unrelated keys can exhaust sshd's `MaxAuthTries` before paddock's own key is ever tried.
- `cli.py` — the typer app; `main` is a single command (no subcommand verbs) taking `--build/--remove/--start/--stop/--restart` as mutually exclusive standalone actions, or none of them for the default build-if-needed/start-if-needed/attach flow.

### Error handling convention

Each layer raises its own typed exception: `ConfigError` (config), `DockerError` (container), `SshError` (ssh). The CLI is the only place that handles them — it catches each and calls `_fail`, which prints a red `error:` message to stderr and raises `typer.Exit(code=1)`. Keep error messages in the lower layers; keep `typer`/exit handling in `cli.py`.

## Testing

Tests cover pure logic only: `config`'s single-file load/env resolution, and `ssh`'s keypair generation/ssh-config writing (against a fake `XDG_STATE_HOME`, real `ssh-keygen` subprocess but no network). `container.py` is intentionally thin and is **not** exercised against a real daemon. Tests point `XDG_CONFIG_HOME`/`XDG_STATE_HOME` at a `tmp_path` fixture tree (see `tests/conftest.py`) rather than touching real config/state. `command:`-based env values are tested with shell builtins like `echo`/`exit`.

## Dependency policy

`pyproject.toml` sets `[tool.uv] exclude-newer = "2 weeks ago"` — a rolling supply-chain delay so freshly published (possibly compromised) releases are ignored until they have had two weeks to be vetted. This is evaluated at each resolution, so re-running `uv lock` naturally picks up releases as they age past the window. `uv.lock` is committed.
