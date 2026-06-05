# paddock

Build, run, and remove a per-repo development container, with environment variables (such as a GitLab PAT) injected from merged config.

Each repo gets its own `Dockerfile` and optional `settings.yaml` files under XDG config. The repo's full path is the convention: it maps directly to a directory tree and to a Docker image tag, so there is no name-to-image mapping to maintain.

## Install

Install it as a tool with [uv](https://docs.astral.sh/uv/):

```sh
uv tool install git+https://github.com/kris-steinhoff/paddock
paddock --help
```

## Usage

```sh
paddock build <repo>          # build the image from the repo's Dockerfile
paddock run <repo> [--build]  # run the image with configured env injected
paddock remove <repo>         # remove the built image
```

`<repo>` is the full repo path, for example `github.com/kris-steinhoff/paddock`. `run` errors if the image has not been built yet, unless you pass `--build` to build it first.

## Configuration

Config lives under `${XDG_CONFIG_HOME:-$HOME/.config}/paddock`. The `repos/` subtree mirrors each repo's full path, so host + org + name uniquely identify a project:

```
~/.config/paddock/
  repos/
    settings.yaml            # global defaults, merged into every project
    github.com/
      settings.yaml          # per-provider
      kris-steinhoff/
        settings.yaml        # per-org (optional)
        paddock/
          Dockerfile
          settings.yaml      # per-project
```

`paddock run github.com/kris-steinhoff/paddock` builds and runs the image tagged `paddock/github.com/kris-steinhoff/paddock` from `repos/github.com/kris-steinhoff/paddock/Dockerfile`. The repo argument splits on `/` to arbitrary depth, so GitLab subgroups (`gitlab.com/org/subgroup/project`) work with no special handling.

### settings.yaml

Optional at every directory level from `repos/` down to the leaf. Files are deep-merged, least specific first, and the most specific file wins per environment-variable key. So you can set a PAT once at the provider level and override it for one org or project.

The top level is a hash with an `environment` key. Each member names an environment variable. A string value is used directly:

```yaml
environment:
  GITLAB_PAT: "my secret"
```

A hash value must have a `command` key, run via `sh -c`. Its stdout (trailing newline stripped) becomes the value:

```yaml
environment:
  GITLAB_PAT:
    command: op read op://Private/Gitlab-PAT/token
```

Each configured variable is passed to the container with its own `docker run -e` flag.

## Development

The project is managed with [uv](https://docs.astral.sh/uv/):

```sh
uv sync                       # install deps and create the venv
uv run paddock --help
uv run ruff format .          # format
uv run ruff check .           # lint
uv run ty check               # type check
uv run pytest                 # test
```

See [SPEC.md](SPEC.md) for the design and [PLAN.md](PLAN.md) for the build plan.
