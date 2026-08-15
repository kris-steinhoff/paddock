# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What paddock is

A uv-managed Python CLI that is a thin `docker compose` driver for a single
general-purpose development container. Its whole job is assembling the right
`docker compose` invocation (packaged base compose file, optional per-machine
override, `PADDOCK_*` interpolation variables), then shelling out and turning
failures into clean errors. One Dockerfile and one compose file ship baked into
the paddock package itself, so there's no per-repo image or config tree.
Connecting to the running container is the user's own business: paddock runs no
client, generates no keys, and touches no ssh config. See `README.md` for
user-facing usage and the config-dir layout.

## Commands

Everything runs through `uv`:

- `uv sync` installs deps and creates `.venv`.
- `uv run paddock [build|up|down|start|stop|restart|status|logs|compose]` invokes the CLI. Bare `paddock` prints help and exits 0. There is no default action.
- `uv run ruff format .` formats. `uv run ruff check .` lints.
- `uv run ty check` type checks.
- `uv run pytest` runs all tests. Single test: `uv run pytest tests/test_compose.py::test_interpolation_env_always_sets_authorized_keys`.

Requires Python >= 3.13. The only runtime dependency is `typer`. `ruff`, `ty`, and `pytest` are dev dependencies (run them via `uv run`, not `uvx`). `docker` is not checked up front. A missing `docker` executable surfaces as a `ComposeError` from the first `compose.run`/`compose.exec_` call, caught by `cli.py` like any other compose failure.

## Architecture

Four modules, plus `image/` (Dockerfile, docker-compose.yml, entrypoint.sh, sshd_config) packaged alongside them.

- `paths.py`: the single place that knows the config-dir layout and the packaged-image location. `config_dir()` (`${XDG_CONFIG_HOME:-~/.config}/paddock`), `compose_file()` (the packaged `image/docker-compose.yml`, resolved off `__file__`), and `override_file()`/`env_file()`/`authorized_keys_path()`/`certs_dir()`, all under `config_dir()`. These are path predicates only, with no existence checks, no error messages, and no exception type of their own. Deliberately **no** XDG state dir: paddock keeps no state, docker owns all of it (images, containers, volumes).
- `compose.py`: the `docker compose` driver behind every `cli.py` subcommand. Two pure functions plus a thin runner. `compose_args(subcommand_args)` builds `docker compose -f <packaged file> [-f <override>] [--env-file <config .env>] <subcommand_args>`, base file first so its directory sets the compose project directory, override second so it wins, both flags added only when the corresponding file exists. `interpolation_env(refresh_tools)` starts from `os.environ` (so the compose file's valueless pass-through entries like `GITHUB_TOKEN` still pick up the user's shell) and layers on `PADDOCK_AUTHORIZED_KEYS` (always), `PADDOCK_CA_CONTEXT` (only when `certs_dir()` holds at least one `*.crt`, otherwise left unset so the compose file's packaged-empty-directory default applies), and `PADDOCK_TOOLS_REFRESH` (only when `refresh_tools`, otherwise left unset so the compose default of `0` reuses the build cache). It never overwrites a variable the user already set in their own shell, `PADDOCK_SSH_PORT`/`PADDOCK_HTTP_PORT` included, since those are pass-through only and paddock itself never sets them. `run()` wraps `subprocess.run`. `exec_()` wraps `os.execvpe` and is used where paddock has no further work once the child starts (`logs`, `compose` passthrough) so signals and the terminal go straight to it. Both raise `ComposeError` rather than a raw traceback for a missing `docker` executable or a non-zero exit. **Gotcha**: `--env-file` feeds compose *interpolation* only (the `${VAR:-default}` substitutions inside the compose file, e.g. the port variables). It is **not** a way to inject arbitrary environment into the container. Container environment comes only from the compose file's `environment:`/`env_file:` keys, so anything new has to go in the user's override file, not in `.env`.
- `cli.py`: the typer app, one subcommand per compose verb, plus `init`. `init` creates `config_dir()` and `certs_dir()` if missing (idempotent: a no-op with a message if they already exist) and prints a nudge toward populating `authorized_keys` if it's still absent; it doesn't create `authorized_keys` itself, since an empty file would silently defeat `_warn_if_no_authorized_keys()`'s existence check. `build [--cached] [--no-cache]`, `up [--build] [--cached]` (always `-d`, since there's no attach story), `down [--volumes]` (`--volumes` forwards `-v` and is the only path that can remove volumes, since that destroys `agent_home`), `start`/`stop`/`restart`, `status` (compose `ps` plus the resolved published ssh port, via `_resolve_ssh_port()`, which mirrors compose's own precedence of shell env, then the config dir's `.env`, then the packaged default), `logs [-f]`, and `compose` (passthrough, execs `docker compose` with whatever follows `--`, e.g. `paddock compose -- exec agent zsh`). No subcommand is a default: bare `paddock` prints help and exits 0, with the app callback checking `ctx.invoked_subcommand is None` itself rather than relying on Typer/Click's `no_args_is_help`, which in current Click exits 2. `up`/`start`/`restart` call `_warn_if_no_authorized_keys()` first: since `interpolation_env` always sets `PADDOCK_AUTHORIZED_KEYS` to the config path whether or not it exists, a missing file is not a compose error, just a container that starts fine and accepts no key, so this is a non-fatal yellow warning rather than a hard failure (paddock doesn't know the caller isn't just planning to use `paddock compose -- exec agent zsh` instead). `build` doesn't check it, since building doesn't start anything. No preflight check was added for a missing `docker`/compose plugin: `ComposeError`'s existing message already covers the missing-executable case cleanly, and a missing compose plugin surfaces docker's own stderr passed straight through by `subprocess.run`/`os.execvpe`, so a redundant check would add a subprocess call for no real gain.
- `image/`: vendored from [agent-container](https://github.com/kris-steinhoff/agent-container). The Dockerfile builds on `node:24-trixie-slim`. `docker-compose.yml` (project `name: paddock`) declares the `agent` service, the two named volumes, the published ports, and the `ca-certificates` named build context. Since these ship read-only inside site-packages, every path or port that would normally be hand-edited is a `${PADDOCK_*:-default}` interpolation instead, and per-machine changes go in the user's override file.

### The tools cache gate

The Dockerfile is split by `ARG TOOLS_REFRESH=0` plus an `echo` of its value. Docker only cache-misses an ARG on its first *use*, not its declaration, so that `echo` is the real gate: it and every layer below it rebuild when the value changes. Everything above the gate stays cached (apt packages, `gh`, `glab`, `terraform`, `neovim`, `chezmoi`, `starship`, `opencode`, and the `chezmoi apply` dotfiles bootstrap with its expensive nvim plugin pre-fetch). Everything below it tracks latest (`herdr`, `claude`, `copilot`, `codex`, `bd`). `docker-compose.yml` forwards `PADDOCK_TOOLS_REFRESH` into the arg and defaults it to `0`, which reuses the cache. `cli.py` asks `compose.interpolation_env` for a fresh `int(time.time())` value on `build` and on `up --build`, unless `--cached` is passed. Moving a tool across that line is the whole knob for "should this pin or track latest".

### The /etc/ssh named-volume gotcha

`/etc/ssh` is the `sshd_host_keys` volume, so host keys survive container recreation. Docker only seeds a named volume from the image on its *first* use, and after that the volume's own content always wins over the image. A config file placed directly under `/etc/ssh` by the Dockerfile (e.g. `sshd_config.d/paddock.conf`) would therefore be silently frozen at whatever the volume was first created with, and no later image rebuild would ever update it. So `sshd_config` is baked in at `/etc/paddock/sshd_config`, outside `/etc/ssh`, and `entrypoint.sh` copies it into `/etc/ssh/sshd_config.d/paddock.conf` on **every** container start. `entrypoint.sh` uses the same start-time-copy pattern for `authorized_keys`, for a different reason: the mounted source is read-only and owned by whatever uid it has on the host, which fails sshd's `StrictModes` check, so it is copied to `/home/agent/.ssh/authorized_keys` and chowned/chmodded there.

### Error handling convention

`compose.py` is the only lower layer with an exception of its own: `ComposeError`, raised for a missing `docker` executable or a non-zero compose exit. `paths.py` raises nothing. The CLI is the only place that handles errors. `_run_compose`/`_exec_compose` catch `ComposeError` and call `_fail`, which prints a red `error:` message to stderr and raises `typer.Exit(code=1)`. Keep error messages in the lower layers, and keep `typer`/exit handling in `cli.py`. A new lower layer should follow the same shape: its own exception type, its own message text, caught and turned into an exit code only in `cli.py`.

## Testing

`uv run pytest` covers pure logic only and never talks to a docker daemon.

- `tests/test_paths.py`: the path helpers, against a fake `XDG_CONFIG_HOME`.
- `tests/test_compose.py`: `compose_args` (with and without override/`.env`, and their ordering) and `interpolation_env` (authorized-keys always set, CA context only for a `*.crt`, tools refresh only on request, user-set variables never clobbered). `run`/`exec_` are exercised with shell builtins (`sh -c 'exit 0'` / `'exit 1'`) and a nonexistent executable, never a real `docker`.
- `tests/test_cli.py`: drives the typer app with `typer.testing.CliRunner` and monkeypatches `compose.run`/`compose.exec_` to capture the argv and env each subcommand would send, rather than shelling out. This is where the flag-to-argv mapping, the `run` vs `exec_` choice, `status`'s port resolution, and the `ComposeError` to `error:`/exit-1 path are pinned.

Tests point `XDG_CONFIG_HOME` at a `tmp_path` tree (the `xdg_base` fixture in `tests/conftest.py`) rather than touching real config. There's no `XDG_STATE_HOME` fixture since paddock has no state dir.

The container itself is covered by two scripts rather than by pytest, both smoke tests of the `/etc/ssh` workaround above. `scripts/verify-entrypoint.sh` builds and runs the real thing under an isolated compose project and image tag, so it needs a Docker daemon, which paddock's own dev container does not have. `scripts/verify-entrypoint-local.sh` replays the same entrypoint commands against a scratch tree under `$HOME` and starts a real sshd against it, so it needs no daemon. The first is the higher-fidelity check and should be preferred wherever a daemon is reachable.

## Dependency policy

`typer` is the only runtime dependency. `pydantic` and `pyyaml` went away with the `settings.yaml` config layer, so don't reach for them (or for a config-file parser generally) without deciding that layer should come back.

`pyproject.toml` sets `[tool.uv] exclude-newer = "2 weeks ago"`, a rolling supply-chain delay so freshly published (possibly compromised) releases are ignored until they have had two weeks to be vetted. This is evaluated at each resolution, so re-running `uv lock` naturally picks up releases as they age past the window. `uv.lock` is committed.

## Issue tracking

Remaining work lives in `TODO.md`. This project previously used beads (`bd`), which has been removed. The old issue ids (`paddock-96h`, `paddock-aye`, `paddock-3t0` and their children) still appear in git history and in `TODO.md` as labels. The last exported snapshot of that tracker is `.beads/issues.jsonl` as of commit `5b25cfb`, if any of it is ever needed again.
