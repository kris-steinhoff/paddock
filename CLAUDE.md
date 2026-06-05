# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What paddock is

A uv-managed Python CLI that builds, runs, and removes a per-repo development container, injecting environment variables (such as a GitLab PAT) resolved from merged config. See `README.md` for user-facing usage and the config format.

## Commands

Everything runs through `uv`:

- `uv sync` — install deps and create `.venv`.
- `uv run paddock <build|run|remove> <repo>` — invoke the CLI (`run` takes `--build`).
- `uv run ruff format .` — format. `uv run ruff check .` — lint.
- `uv run ty check` — type check.
- `uv run pytest` — run all tests. Single test: `uv run pytest tests/test_config.py::test_command_value_resolved`.

Requires Python >= 3.13. `ruff`, `ty`, and `pytest` are dev dependencies (run them via `uv run`, not `uvx`).

## Architecture

Four small modules under `src/paddock/`, each owning one stage of the pipeline:

- `resolver.py` — turns a `<repo>` argument into a `RepoTarget`. The repo path *is* the convention: it splits on `/` to arbitrary depth (so GitLab subgroups need no special handling) and maps directly to `repos/<path>/Dockerfile` and a lowercased `paddock/<path>` image tag. There is deliberately no name-to-image mapping file. It also computes `settings_paths`: one `settings.yaml` per directory level from `repos/` down to the leaf, ordered least to most specific, existing files only.
- `config.py` — pydantic models plus settings merge and env resolution. `load_merged` deep-merges each `settings.yaml` (most specific wins per `environment`/`volumes` key) and validates with `extra="forbid"`. `resolve_environment` turns each value into a string: a literal is used as-is, a `{command: ...}` is run via `sh -c` with stdout's trailing newline stripped. The optional `volumes` hash maps a merge-key to a raw `docker run -v` spec: `volume_args` returns those strings verbatim for `run`, and `named_volumes` applies docker's `-v` heuristic (bare source = named volume) to pick which to delete on `remove`.
- `docker.py` — thin list-form `subprocess` wrappers (no shell) for `docker build/run/image inspect/rmi/volume rm`.
- `cli.py` — the typer app wiring the above into `build`, `run [--build]`, `remove` (which also deletes the configured named volumes).

### Error handling convention

Each layer raises its own typed exception: `RepoError` (resolver), `ConfigError` (config), `DockerError` (docker). The CLI is the only place that handles them — it catches each and calls `_fail`, which prints a red `error:` message to stderr and raises `typer.Exit(code=1)`. Keep error messages in the lower layers; keep `typer`/exit handling in `cli.py`.

## Testing

Tests cover pure logic only (`resolver` path/tag computation and the `config` merge/env resolution). `docker.py` is intentionally thin and is **not** exercised against a real daemon. Tests point `XDG_CONFIG_HOME` at a `tmp_path` fixture tree (see `tests/conftest.py`) rather than touching real config. `command:`-based env values are tested with shell builtins like `echo`/`exit`.

## Dependency policy

`pyproject.toml` sets `[tool.uv] exclude-newer = "2 weeks ago"` — a rolling supply-chain delay so freshly published (possibly compromised) releases are ignored until they have had two weeks to be vetted. This is evaluated at each resolution, so re-running `uv lock` naturally picks up releases as they age past the window. `uv.lock` is committed.
