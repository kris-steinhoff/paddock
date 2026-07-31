# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What paddock is

A uv-managed Python CLI that wraps a single general-purpose development
container (build/start/stop/restart/remove). One Dockerfile ships baked into
the paddock package itself — there's no per-repo image or config tree.
Connecting to the running container is the user's own business; paddock
doesn't touch it. See `README.md` for user-facing usage and the config
format.

## Commands

Everything runs through `uv`:

- `uv sync` — install deps and create `.venv`.
- `uv run paddock [--build|--start|--stop|--restart|--remove]` — invoke the CLI. Bare `paddock` builds/starts as needed.
- `uv run ruff format .` — format. `uv run ruff check .` — lint.
- `uv run ty check` — type check.
- `uv run pytest` — run all tests. Single test: `uv run pytest tests/test_config.py::test_command_value_resolved`.

Requires Python >= 3.13. `ruff`, `ty`, and `pytest` are dev dependencies (run them via `uv run`, not `uvx`). `docker` must be on `PATH` at runtime (checked up front in `cli.py`).

## Architecture

- `paths.py` — the single place that knows the config-dir layout and the packaged-image location: `config_dir()` (`${XDG_CONFIG_HOME:-~/.config}/paddock`), `compose_file()` (the packaged `image/docker-compose.yml`, resolved off `__file__` the same way `container.IMAGE_DIR` is), and `override_file()`/`env_file()`/`authorized_keys_path()`/`certs_dir()`, all under `config_dir()`. These are path predicates only — no existence checks, no error messages. Deliberately **no** XDG state dir: paddock keeps no state of its own, docker owns all of it (images, containers, volumes).
- `compose.py` — the `docker compose` driver that will replace `container.py` (not yet wired into `cli.py`; that's a separate rework). Two pure functions plus a thin runner: `compose_args(subcommand_args)` builds `docker compose -f <packaged file> [-f <override>] [--env-file <config .env>] <subcommand_args>` — base file first so its directory sets the compose project directory, override second so it wins, both flags added only when the corresponding file exists. `interpolation_env(refresh_tools)` starts from `os.environ` (so the compose file's valueless pass-through entries like `GITHUB_TOKEN` still pick up the user's shell) and layers on `PADDOCK_AUTHORIZED_KEYS` (always), `PADDOCK_CA_CONTEXT` (only when `certs_dir()` holds at least one `*.crt`, otherwise left unset so the compose file's packaged-empty-directory default applies), and `PADDOCK_TOOLS_REFRESH` (only when `refresh_tools`, otherwise left unset so the compose default of `0` reuses the build cache) — it never overwrites a variable the user already set in their own shell, `PADDOCK_SSH_PORT`/`PADDOCK_HTTP_PORT` included, since those are pass-through only and paddock itself never sets them. `run()`/`exec_()` wrap `subprocess`/`os.execvpe` and raise `ComposeError` (not a raw traceback) for a missing `docker` executable or a non-zero exit. **`--env-file` feeds compose *interpolation* only** (the `${VAR:-default}` substitutions inside the compose file, e.g. the port variables above) — it is not a way to inject arbitrary environment into the container; container environment belongs in the compose file's `environment:`/`env_file:` keys.
- `config.py` — pydantic models plus single-file load and env resolution. `load_settings` reads one optional `settings.yaml` (missing file = empty settings) and validates with `extra="forbid"`. `resolve_environment` turns each value into a string: a literal is used as-is, a `{command: ...}` is run via `sh -c` with stdout's trailing newline stripped. `ca_certificate_paths` expands (`~`) and validates each `ca_certificates` entry exists, raising `ConfigError` early rather than failing deep inside a docker build.
- `container.py` — thin list-form `subprocess` wrappers (no shell) around `docker build/run/start/stop/restart/rm/rmi`, scoped to the one fixed `paddock` image/container name. `IMAGE_DIR` resolves to the `image/` directory baked into the installed package (Dockerfile, entrypoint.sh, sshd_config — adapted from `../agent-container`). `build()` assembles a fresh temp build context per call (copies `IMAGE_DIR` plus a `ca-certificates/` dir populated from any configured CA paths) rather than building `IMAGE_DIR` directly, since the installed package directory shouldn't be mutated and CA cert paths live outside it. `set_environment()` writes resolved `environment:` values into `~/.ssh/environment` inside the container via `docker exec` (piped over stdin, not baked in at `docker run -e` time) — sshd (`PermitUserEnvironment yes` in `sshd_config`) reads that file fresh per new session, so edited `settings.yaml` values reach the container on the next shell/session without restarting or recreating it, which would kill anything already running inside. `cli.py`'s default (no-flag) path calls `_start()` unconditionally, even when already running, specifically so this refresh happens on every plain `paddock` invocation. **Gotcha**: `/etc/ssh` is the `paddock_ssh_host_keys` volume (so host keys survive container recreation), and Docker only seeds a named volume from the image on its *first* use — a config file placed directly under `/etc/ssh` by the Dockerfile (e.g. `sshd_config.d/paddock.conf`) would silently never be updated by a later image rebuild once that volume already exists, since the volume's stale content always wins. So `sshd_config` is baked into the image at `/etc/paddock/sshd_config` (outside `/etc/ssh`) and `entrypoint.sh` copies it into `/etc/ssh/sshd_config.d/paddock.conf` on every container start, the same pattern already used there for `authorized_keys`.
- `cli.py` — the typer app; `main` is a single command (no subcommand verbs) taking `--build/--remove/--start/--stop/--restart` as mutually exclusive standalone actions, or none of them for the default build-if-needed/start-if-needed flow. `_start()` sources the mounted `authorized_keys` from `paths.authorized_keys_path()` directly — the user is expected to populate that file themselves; paddock no longer generates a keypair.

### Error handling convention

Each layer raises its own typed exception: `ConfigError` (config), `DockerError` (container), `ComposeError` (compose). The CLI is the only place that handles them — it catches each and calls `_fail`, which prints a red `error:` message to stderr and raises `typer.Exit(code=1)`. Keep error messages in the lower layers; keep `typer`/exit handling in `cli.py`.

## Testing

Tests cover pure logic only: `paths`'s helpers, `compose`'s `compose_args`/`interpolation_env`, and `config`'s single-file load/env resolution. `compose.run`/`compose.exec_` are exercised with shell builtins (`sh -c exit 0/1`, a nonexistent executable), never a real `docker`; `container.py` is likewise intentionally thin and **not** exercised against a real daemon. Tests point `XDG_CONFIG_HOME` at a `tmp_path` fixture tree (see `tests/conftest.py`) rather than touching real config; there's no `XDG_STATE_HOME` fixture since paddock has no state dir. `command:`-based env values are tested with shell builtins like `echo`/`exit`.

## Dependency policy

`pyproject.toml` sets `[tool.uv] exclude-newer = "2 weeks ago"` — a rolling supply-chain delay so freshly published (possibly compromised) releases are ignored until they have had two weeks to be vetted. This is evaluated at each resolution, so re-running `uv lock` naturally picks up releases as they age past the window. `uv.lock` is committed.

## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Rules

- Use `bd` for ALL task tracking
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export.

