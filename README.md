# paddock

Build, start, stop, and remove a single general-purpose development
container, and attach to it with [herdr](https://herdr.dev). One Dockerfile
ships with paddock itself (no per-repo image to author) — the same
container every time, mirroring the pattern in
[agent-container](https://github.com/kris-steinhoff/agent-container) but
orchestrated directly by paddock instead of docker-compose.

Ships: `claude`, `opencode`, `neovim`, `gh`, `glab`, `uv`, `chezmoi`, and
`sshd` so herdr can attach to a persistent session inside the container.

## Install

Install it as a tool with [uv](https://docs.astral.sh/uv/):

```sh
uv tool install git+https://github.com/kris-steinhoff/paddock
paddock --help
```

Requires `docker` and `herdr` installed and on `PATH`.

## Usage

```sh
paddock            # build if needed, start if needed, attach with herdr
paddock --build    # (re)build the image
paddock --start     # create/start the container without attaching
paddock --stop      # stop the container
paddock --restart   # restart the container
paddock --remove    # stop and remove the container and image (volumes are kept)
```

The flags are standalone actions and mutually exclusive; only bare `paddock`
attaches. To rebuild and reattach: `paddock --build && paddock`.

## SSH

paddock generates its own dedicated ed25519 keypair on first use, under
`${XDG_STATE_HOME:-~/.local/state}/paddock/ssh_home/.ssh/`. The public key is
mounted into the container as its `authorized_keys`; nothing is added to
your own `~/.ssh`.

Attaching runs `herdr --remote ssh://agent@localhost:2223` with `HOME`
pointed at that same directory for just that one subprocess call, so herdr's
managed ssh config, known_hosts, and identity file resolution are all scoped
to paddock's own directory instead of your real `~/.ssh/config`.

## Persistence

Two named docker volumes persist across `--stop`/`--restart` and container
recreation:

- `paddock_home` → `/home/agent` — dotfiles, shell history, tool auth
  (`claude`, `gh`, etc.)
- `paddock_ssh_host_keys` → `/etc/ssh` — sshd's host keys, so rebuilding the
  image doesn't change the container's host key and trip
  `StrictHostKeyChecking`

`paddock --remove` removes the container and image but leaves both volumes
in place. Delete them yourself with `docker volume rm paddock_home
paddock_ssh_host_keys` if you want a truly clean slate.

## Credentials

Not baked into the image. Either:

- Run `claude` / `opencode` / `gh auth login` inside the container once and
  complete the normal interactive login, which persists in the
  `paddock_home` volume, or
- Set environment variables in `settings.yaml` (see below), injected via
  `docker run -e` at container start.

## Configuration

A single optional file:
`${XDG_CONFIG_HOME:-~/.config}/paddock/settings.yaml`.

```yaml
environment:
  ANTHROPIC_API_KEY: "sk-..."
  GITLAB_PAT:
    command: op read op://Private/Gitlab-PAT/token
```

Each member names an environment variable. A string value is used directly.
A hash value must have a `command` key, run via `sh -c`; its stdout (trailing
newline stripped) becomes the value. Since the command runs through a shell,
you can pipe to extract a single value:

```yaml
environment:
  AWS_SESSION_TOKEN:
    command: aws configure export-credentials | jq -r .SessionToken
```

Each configured variable is passed to the container with its own
`docker run -e` flag whenever it's (re)started.

### Corporate CA certificates

If your network runs a TLS-intercepting proxy, list its root CA(s) under
`ca_certificates`:

```yaml
ca_certificates:
  - ~/corp/proxy-ca.pem
```

Paths are expanded (`~` works) and must exist — `paddock --build` fails fast
with a clear error otherwise, rather than deep inside a docker build. Each
listed certificate is copied into the build context and trusted via
`update-ca-certificates` **before** any other networked step in the
Dockerfile (apt/curl/npm), so it covers both the image build and everything
the running container does afterward — the built image already carries the
trust, no runtime mount needed. Node-based tools (`claude`, `opencode`,
`npm`) and some Python tooling ignore the system trust store by default, so
the image also pins `NODE_EXTRA_CA_CERTS`, `SSL_CERT_FILE`,
`REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE`, `PIP_CERT`, and `GIT_SSL_CAINFO` at
the merged system bundle.

Changing `ca_certificates` requires `paddock --build` to take effect (it's
baked into the image, not read at container start). This only covers CA
trust — if your network also requires an `HTTP_PROXY`/`HTTPS_PROXY` to reach
the network *during the build itself*, that's not wired up yet (proxy env
vars for the running container can already go in `environment` above).

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
