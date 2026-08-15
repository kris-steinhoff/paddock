# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What paddock is

A uv-managed Python CLI that is a thin `docker compose` driver for a single
general-purpose development container. Its whole job is assembling the right
`docker compose` invocation (packaged base compose file, optional per-machine
override, `PADDOCK_*` interpolation variables), then handing the process over
to compose. It wraps no compose verb: everything after `--` passes through
untouched. One Dockerfile and one compose file ship baked into
the paddock package itself, so there's no per-repo image or config tree.
Connecting to the running container is the user's own business: paddock runs no
client, generates no keys, and touches no ssh config. See `README.md` for
user-facing usage and the config-dir layout.

## Commands

Everything runs through `uv`:

- `uv sync` installs deps and creates `.venv`.
- `uv run paddock -- <compose args>` invokes the CLI, e.g. `uv run paddock -- up -d`. Everything after `--` goes to `docker compose` untouched. paddock's own flags (`--init`, `--refresh`/`--no-refresh`, `--version`, `--help`) go before it. Bare `paddock` prints help and exits 0. The `--` is required: `paddock up` is an error, not a shortcut.
- `uv run ruff format .` formats. `uv run ruff check .` lints.
- `uv run ty check` type checks.
- `uv run pytest` runs all tests. Single test: `uv run pytest tests/test_compose.py::test_interpolation_env_always_sets_authorized_keys`.

Requires Python >= 3.13. The only runtime dependency is `typer`. `ruff`, `ty`, and `pytest` are dev dependencies (run them via `uv run`, not `uvx`). `docker` is not checked up front. A missing `docker` executable surfaces as a `ComposeError` from `compose.exec_`, caught by `cli.py`.

## Architecture

Four modules, plus `image/` (Dockerfile, docker-compose.yml, entrypoint.sh, sshd_config) packaged alongside them.

- `paths.py`: the single place that knows the config-dir layout and the packaged-image location. `config_dir()` (`${XDG_CONFIG_HOME:-~/.config}/paddock`), `compose_file()` (the packaged `image/docker-compose.yml`, resolved off `__file__`), and `override_file()`/`env_file()`/`authorized_keys_path()`/`certs_dir()`, all under `config_dir()`. These are path predicates only, with no existence checks, no error messages, and no exception type of their own. Deliberately **no** XDG state dir: paddock keeps no state, docker owns all of it (images, containers, volumes).
- `compose.py`: the `docker compose` driver behind every `cli.py` subcommand. Two pure functions plus a thin runner. `compose_args(subcommand_args)` builds `docker compose -f <packaged file> [-f <override>] [--env-file <config .env>] <subcommand_args>`, base file first so its directory sets the compose project directory, override second so it wins, both flags added only when the corresponding file exists. `interpolation_env(refresh_tools)` starts from `os.environ` (so the compose file's valueless pass-through entries like `GITHUB_TOKEN` still pick up the user's shell) and layers on `PADDOCK_AUTHORIZED_KEYS` (always), `PADDOCK_CA_CONTEXT` (only when `certs_dir()` holds at least one `*.crt`, otherwise left unset so the compose file's packaged-empty-directory default applies), and `PADDOCK_TOOLS_REFRESH` (only when `refresh_tools`, otherwise left unset so the compose default of `0` reuses the build cache). It never overwrites a variable the user already set in their own shell, `PADDOCK_SSH_PORT`/`PADDOCK_HTTP_PORT` included, since those are pass-through only and paddock itself never sets them. `exec_()` wraps `os.execvpe` and is the only runner: every paddock invocation is a passthrough, so paddock never has work left once the child starts. Signals and the terminal go straight to compose, and compose's exit code and error messages reach the user unmediated instead of being re-reported behind a second paddock-level error. It raises `ComposeError` rather than a raw traceback for a missing `docker` executable. (v3 also had a `run()` wrapping `subprocess.run` for the non-passthrough subcommands; it went away with them, and with it the non-zero-exit branch of `ComposeError`, which `exec` makes unnecessary.) **Gotcha**: `--env-file` feeds compose *interpolation* only (the `${VAR:-default}` substitutions inside the compose file, e.g. the port variables). It is **not** a way to inject arbitrary environment into the container. Container environment comes only from the compose file's `environment:`/`env_file:` keys, so anything new has to go in the user's override file, not in `.env`.
- `cli.py`: a typer app with exactly **one** command, which is a `docker compose` passthrough. It wraps no compose verb — v3 had one subcommand per verb, and that surface turned out to be all cost: it re-exposed compose 1:1, made `up` vs `start` a decision the user had to make for no benefit, and printed a redundant second `error:` line under compose's own perfectly clear failure message. Registering a single `@app.command()` with `context_settings={"ignore_unknown_options": True, "allow_extra_args": True}` makes Typer a single-command CLI (no verb to name), and declaring a variadic `typer.Argument` rather than reading `ctx.args` is what puts `[ARGS]...` in the help output. Naming the command function `paddock` is what makes the usage line read `Usage: paddock ...`.
  - **The `--` is required, and detecting it takes `sys.argv`.** Click consumes the `--` separator without recording that it saw one, so the parsed `args` alone can't distinguish `paddock -- start` from `paddock start`. `_passthrough_args(argv)` re-reads `sys.argv[1:]` and returns the slice after the first `--`, or `None` when there is none; when a separator is present that slice matches Click's own parse exactly, so the declared `Argument` exists purely for parsing and help text. Args with no separator call `_fail()`. Requiring the separator is what keeps paddock's flags and compose's from ever being confused for one another. The consequence for tests is that they must set `sys.argv` alongside the `CliRunner` args — `tests/test_cli.py` has an `invoke()` helper that does both.
  - `--init` calls `_init()`, which creates `config_dir()` and `certs_dir()` if missing (idempotent: a message and no-op otherwise) and nudges toward populating `authorized_keys` without creating it, since an empty file would silently defeat `_warn_if_no_authorized_keys()`'s existence check. It then falls through to the passthrough if args were given (`paddock --init -- up` works), so no argument is ever silently ignored; `--init` alone exits 0 without dumping help.
  - `--refresh/--no-refresh` defaults to **refresh**. paddock no longer knows which verb you're running, so rather than sniffing the passthrough args for `build` it sets a fresh `PADDOCK_TOOLS_REFRESH` on every invocation. This was expected to cost spurious container recreation (the theory being that compose folds build args into the container's config hash), which is why `--no-refresh` exists. **Verified against a real daemon: it does not.** Back-to-back `paddock -- up -d` calls report `Running`, not `Recreated` — the config hash is computed against the built image, and an unchanged image means an unchanged hash no matter what the build arg says. So the default is free, and `--no-refresh` matters only for reusing the cached tool-install layer on a `build`. Don't re-introduce arg-sniffing to "fix" a cost that isn't there.
  - `_warn_if_no_authorized_keys()` fires on any passthrough, not per-verb (there are no verbs to key off). Since `interpolation_env` always sets `PADDOCK_AUTHORIZED_KEYS` whether or not the file exists, a missing file is not a compose error, just a container that starts fine and accepts no key — hence a non-fatal yellow warning rather than a hard failure.
  - No preflight check for a missing `docker`/compose plugin: `ComposeError` already covers the missing-executable case, and a missing compose plugin surfaces docker's own stderr directly, so a check would add a subprocess call for nothing.
- `image/`: vendored from [agent-container](https://github.com/kris-steinhoff/agent-container). The Dockerfile builds on `node:24-trixie-slim`. `docker-compose.yml` (project `name: paddock`) declares the `agent` service, the two named volumes, the published ports, and the `ca-certificates` named build context. Since these ship read-only inside site-packages, every path or port that would normally be hand-edited is a `${PADDOCK_*:-default}` interpolation instead, and per-machine changes go in the user's override file.

### The tools cache gate

The Dockerfile is split by `ARG TOOLS_REFRESH=0` plus an `echo` of its value. Docker only cache-misses an ARG on its first *use*, not its declaration, so that `echo` is the real gate: it and every layer below it rebuild when the value changes. Everything above the gate stays cached (apt packages, `gh`, `glab`, `terraform`, `neovim`, `chezmoi`, `starship`, `opencode`, and the `chezmoi apply` dotfiles bootstrap with its expensive nvim plugin pre-fetch). Everything below it tracks latest (`herdr`, `claude`, `copilot`, `codex`, `bd`). `docker-compose.yml` forwards `PADDOCK_TOOLS_REFRESH` into the arg and defaults it to `0`, which reuses the cache. `cli.py` asks `compose.interpolation_env` for a fresh `int(time.time())` value on every invocation, unless `--no-refresh` is passed. Moving a tool across that line is the whole knob for "should this pin or track latest".

### The /etc/ssh named-volume gotcha

`/etc/ssh` is the `sshd_host_keys` volume, so host keys survive container recreation. Docker only seeds a named volume from the image on its *first* use, and after that the volume's own content always wins over the image. A config file placed directly under `/etc/ssh` by the Dockerfile (e.g. `sshd_config.d/paddock.conf`) would therefore be silently frozen at whatever the volume was first created with, and no later image rebuild would ever update it. So `sshd_config` is baked in at `/etc/paddock/sshd_config`, outside `/etc/ssh`, and `entrypoint.sh` copies it into `/etc/ssh/sshd_config.d/paddock.conf` on **every** container start. `entrypoint.sh` uses the same start-time-copy pattern for `authorized_keys`, for a different reason: the mounted source is read-only and owned by whatever uid it has on the host, which fails sshd's `StrictModes` check, so it is copied to `/home/agent/.ssh/authorized_keys` and chowned/chmodded there.

### The container's runtime user

The image's final `USER` is **agent**, and that is load-bearing in a non-obvious way. `docker exec` (and so `paddock -- exec agent zsh`, which `README.md` recommends as the no-ssh shell) uses the image's `USER`. When that was `root` — as it was through 4.0, since the `npm`/beads installs need root to write `/usr/local` — an exec'd shell landed as root in `/home/agent`, which is the persistent `agent_home` volume. Anything run there (`claude`, `gh`, `npm`, `uv`) writes root-owned dotfiles and caches into that volume, and the agent user can't overwrite them afterwards. ssh logins never had this problem, since sshd drops to agent itself.

The catch is that `entrypoint.sh` genuinely needs root: `mkdir /run/sshd`, `ssh-keygen -A` into the `/etc/ssh` volume, copying `sshd_config.d/paddock.conf`, chowning `authorized_keys`, and binding privileged port 22. So the Dockerfile ends `USER agent` and the entrypoint sudos those steps instead (agent has `NOPASSWD:ALL` via `/etc/sudoers.d/agent`). It resolves a `SUDO` variable once from `id -u` rather than hardcoding `sudo`, so it still works if the container is run as root through a `user:` override.

Two consequences to keep in mind when touching either file: the entrypoint now depends on that sudoers file staying correct, and sshd is reached via `exec sudo`, so the signal path is tini → sudo → sshd. `scripts/verify-entrypoint.sh` pins both (criteria 4 and 5) — criterion 5 times the stop, since a broken signal chain shows up only as compose waiting out its full timeout before SIGKILLing.

### Error handling convention

`compose.py` is the only lower layer with an exception of its own: `ComposeError`, raised for a missing `docker` executable. `paths.py` raises nothing. The CLI is the only place that handles errors: it catches `ComposeError` around the `compose.exec_` call and calls `_fail`, which prints a red `error:` message to stderr and raises `typer.Exit(code=1)`. Non-zero compose exits are deliberately *not* paddock's business any more — `exec` hands the process over, so compose's own message and exit code stand on their own. Keep error messages in the lower layers, and keep `typer`/exit handling in `cli.py`. A new lower layer should follow the same shape: its own exception type, its own message text, caught and turned into an exit code only in `cli.py`.

## Testing

`uv run pytest` covers pure logic only and never talks to a docker daemon.

- `tests/test_paths.py`: the path helpers, against a fake `XDG_CONFIG_HOME`.
- `tests/test_compose.py`: `compose_args` (with and without override/`.env`, and their ordering) and `interpolation_env` (authorized-keys always set, CA context only for a `*.crt`, tools refresh only on request, user-set variables never clobbered). `run`/`exec_` are exercised with shell builtins (`sh -c 'exit 0'` / `'exit 1'`) and a nonexistent executable, never a real `docker`.
- `tests/test_cli.py`: drives the typer app with `typer.testing.CliRunner` and monkeypatches `compose.exec_` to capture the argv and env it would send, rather than shelling out. Everything goes through the module-level `invoke()` helper, which sets `sys.argv` alongside the runner args so `_passthrough_args` can see the `--`; a test that calls `runner.invoke` directly will read a stale `sys.argv` and quietly test the wrong thing. This is where the required separator, the passthrough argv assembly, `--init`, the refresh default, the missing-keys warning, and the `ComposeError` to `error:`/exit-1 path are pinned. `_passthrough_args` is also unit-tested directly, being pure.

Tests point `XDG_CONFIG_HOME` at a `tmp_path` tree (the `xdg_base` fixture in `tests/conftest.py`) rather than touching real config. There's no `XDG_STATE_HOME` fixture since paddock has no state dir.

The container itself is covered by two scripts rather than by pytest, both smoke tests of the `/etc/ssh` workaround above. `scripts/verify-entrypoint.sh` builds and runs the real thing under an isolated compose project and image tag, so it needs a Docker daemon, which paddock's own dev container does not have. `scripts/verify-entrypoint-local.sh` replays the same entrypoint commands against a scratch tree under `$HOME` and starts a real sshd against it, so it needs no daemon. The first is the higher-fidelity check and should be preferred wherever a daemon is reachable.

## Dependency policy

`typer` is the only runtime dependency. `pydantic` and `pyyaml` went away with the `settings.yaml` config layer, so don't reach for them (or for a config-file parser generally) without deciding that layer should come back.

`pyproject.toml` sets `[tool.uv] exclude-newer = "2 weeks ago"`, a rolling supply-chain delay so freshly published (possibly compromised) releases are ignored until they have had two weeks to be vetted. This is evaluated at each resolution, so re-running `uv lock` naturally picks up releases as they age past the window. `uv.lock` is committed.

## Issue tracking

Remaining work lives in `TODO.md`. This project previously used beads (`bd`), which has been removed. The old issue ids (`paddock-96h`, `paddock-aye`, `paddock-3t0` and their children) still appear in git history and in `TODO.md` as labels. The last exported snapshot of that tracker is `.beads/issues.jsonl` as of commit `5b25cfb`, if any of it is ever needed again.
