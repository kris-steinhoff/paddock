# paddock

A per-repo `Dockerfile` plus a small CLI that builds, runs, and removes the right container for a repo, with a configured PAT injected as an environment variable. Config lives under XDG paths. Everything else is manual until it annoys.

## Implementation

Python CLI built with [typer](https://typer.tiangolo.com/). Settings models and the merge logic use [pydantic](https://docs.pydantic.dev/). Installed as a `paddock` console script.

### Tooling

- [uv](https://docs.astral.sh/uv/) manages the project (dependencies, virtualenv, running commands).
- [ruff](https://docs.astral.sh/ruff/) handles formatting and linting.
- [ty](https://github.com/astral-sh/ty) handles type checking.
- [pytest](https://docs.pytest.org/) handles testing.

## Layout (XDG)

Base dir is `${XDG_CONFIG_HOME:-$HOME/.config}/paddock`. The `repos/` subtree mirrors each repo's full path, so host + org + name uniquely identify a project. No flat names, no collisions, no mapping file:

```
~/.config/paddock/
  repos/
    settings.yaml            # global defaults, merged into every project
    github.com/
      settings.yaml          # per-provider, for example a PAT that works for all github repos
      kris-steinhoff/
        settings.yaml        # per-org, optional
        paddock/
          Dockerfile
          settings.yaml      # per-project
        another-project/
          Dockerfile
          settings.yaml      # per-project
    gitlab.com/
      ...
```

## Repo -> image: the path is the convention

`paddock run github.com/kris-steinhoff/paddock` resolves to `.../paddock/repos/github.com/kris-steinhoff/paddock/Dockerfile`. Because the full repo path is the key, there is nothing left to disambiguate (the earlier `overrides.yaml` idea is gone).

The repo argument is split on `/` and each segment maps to a directory level, so arbitrarily deep paths work too (for example GitLab subgroups: `gitlab.com/org/subgroup/project`). The `Dockerfile` lives in the leaf directory.

The image is tagged `paddock/<repo-path>`, lowercased. For the example above that is `paddock/github.com/kris-steinhoff/paddock`.

(Optional later nicety: accept a bare `paddock` and resolve it when the basename is unique across the tree.)

## Customization (merged)

Optional `settings.yaml` files at every directory level from `repos/` down to the leaf. The hash structure allows merging: keys from more specific files override the same keys from less specific files. For example, a user can define `repos/github.com/settings.yaml` to set a PAT, then define `repos/github.com/kris-steinhoff/settings.yaml` to override the PAT for projects under that org.

Discovery walks each directory level in the resolved path, least specific first (`repos/settings.yaml`, then `repos/<host>/settings.yaml`, and so on down to the leaf), and deep-merges every `environment` hash it finds. The most specific file wins per environment variable key.

### Format

YAML with a hash-based structure so that overrides are easy to reason about.

The top level is a hash. The one key to start with is `environment`, whose value is also a hash. Each member of the `environment` hash names an environment variable. If the member's value is a string, it is used directly. If the value is a hash, it must have a `command` key whose value is a shell command. The command is run (`sh -c`), and its stdout (trailing newline stripped) becomes the environment variable's value. A non-zero exit fails the run.

```yaml
environment:
  GITLAB_PAT: "my secret"
```

```yaml
environment:
  GITLAB_PAT:
    command: op read op://Private/Gitlab-PAT/token
```

## Commands

Every command takes a `<repo>` argument (the full repo path) and resolves the image tag and Dockerfile from it the same way.

### `paddock build <repo>`

Builds the image from the repo's Dockerfile and tags it:

```sh
docker build -t "$IMAGE" "$DOCKERFILE_DIR"
```

The build context is the directory containing the Dockerfile.

### `paddock run <repo> [--build]`

Resolves the environment from the merged settings and runs the image, passing each configured environment variable through with its own `-e` flag:

```sh
docker run -it --rm -e GITLAB_PAT="configured_value" "$IMAGE"
```

With `--build`, it runs `paddock build` first, then runs. Without `--build`, it runs the existing image and errors if the image has not been built yet.

### `paddock remove <repo>`

Removes the built image:

```sh
docker rmi "$IMAGE"
```

A clean teardown for the image. Containers are disposed by `--rm` when they exit, so there is nothing else to remove.

## Manual for now (toil backlog)

By hand inside the container. Migrate each into the tool independently, whenever it gets tedious:

- clone the repo and cut a branch
- start the agent (`claude` in Auto)
- open the MR, review, merge
