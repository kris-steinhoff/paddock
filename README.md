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
`${XDG_CONFIG_HOME:-~/.config}/paddock/ssh_home/.ssh/`. The public key is
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
- Set environment variables in `settings.yaml` (see below), picked up by
  every new shell/session without needing a container restart.

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

Every `paddock` invocation re-resolves this list and writes it to the
container's `~/.ssh/environment` (readable by sshd only, on the persistent
`paddock_home` volume), so edits take effect for the next new shell/session
without restarting the container or disturbing anything already running
inside it.

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
`update-ca-certificates` right after the base image's first `apt-get install`
(which is what provides the `ca-certificates`/`update-ca-certificates` tooling
in the first place — that one step is unavoidably not covered, so it needs to
reach the network without the corporate CA already trusted, e.g. over a
network path the proxy doesn't intercept), and before every other networked
step in the Dockerfile (curl/npm/further apt). This covers both the image
build from that point on and everything the running container does
afterward — the built image already carries the trust, no runtime mount
needed. Node-based tools (`claude`, `opencode`, `npm`) and some Python
tooling ignore the system trust store by default, so the image also pins
`NODE_EXTRA_CA_CERTS`, `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`,
`CURL_CA_BUNDLE`, `PIP_CERT`, and `GIT_SSL_CAINFO` at the merged system
bundle.

Changing `ca_certificates` requires `paddock --build` to take effect (it's
baked into the image, not read at container start). This only covers CA
trust — if your network also requires an `HTTP_PROXY`/`HTTPS_PROXY` to reach
the network *during the build itself*, that's not wired up yet (proxy env
vars for the running container can already go in `environment` above).

## docker-compose.yml

The image ships with a `docker-compose.yml`, at
`src/paddock/image/docker-compose.yml` inside the installed package. Since
that file lives read-only in site-packages, every path or port that would
normally be hand-edited is instead an environment variable:

- `PADDOCK_SSH_PORT` (default `2222`) and `PADDOCK_HTTP_PORT` (default
  `8000`) — published host ports.
- `PADDOCK_TOOLS_REFRESH` (default `0`) — the `TOOLS_REFRESH` build arg; set
  to a fresh value to bypass the Dockerfile's cache gate for `claude`,
  `copilot`, `codex`, and `herdr`.
- `PADDOCK_CA_CONTEXT` (default `./ca-certificates`, the empty directory
  packaged alongside the compose file) — the `ca-certificates` named build
  context; see [Corporate CA certificates](#corporate-ca-certificates).
- `PADDOCK_AUTHORIZED_KEYS` — path to the public key mounted in as
  `authorized_keys`. Has no default; it must be set for every invocation.

paddock sets these for you: `PADDOCK_AUTHORIZED_KEYS` always, `PADDOCK_CA_CONTEXT`
only when `~/.config/paddock/certs/` holds at least one `*.crt`, and
`PADDOCK_TOOLS_REFRESH` only on an explicit rebuild-with-refresh — otherwise
they're left for the compose file's own defaults or your shell to supply.

These variables can also be set in your shell, or in a `.env` file at
`~/.config/paddock/.env`, which paddock passes to compose via `--env-file`
when present. Note that `--env-file` only feeds *interpolation* — the
`${VAR:-default}` substitutions inside the compose file, like the ports
above — it is not a way to inject arbitrary environment variables into the
container itself. Container environment belongs in the compose file's
`environment:`/`env_file:` keys, which is what a per-machine override file is
for: bind-mounting a project into the container, most commonly, layered on
top with a second `-f` rather than editing the packaged file:

```yaml
# ~/.config/paddock/docker-compose.override.yml
services:
  agent:
    volumes:
      - ~/code/github.com/kris-steinhoff/some-project:/home/agent/workspace/some-project
    environment:
      - EXTRA_TOKEN
```

```sh
docker compose -f src/paddock/image/docker-compose.yml \
  -f ~/.config/paddock/docker-compose.override.yml up -d
```

## Migrating from an older setup

paddock has gone through two earlier shapes: agent-container (a separate,
per-repo compose project) and paddock 2.x (this same project, but driving
`docker build`/`docker run` directly instead of compose). Both left behind a
container, an image, and — the part worth being careful with — a home
volume full of tool auth and shell history. The risk in either migration is
losing that volume by forgetting about it.

### From agent-container

agent-container's compose project was named `agent-container`, so its
volumes are `agent-container_agent_home` and `agent-container_ssh_host_keys`.
Reuse the home volume instead of starting paddock with an empty one, by
declaring paddock's own `agent_home` volume as external and pointing it at
the old name — the same override file used for bind mounts and extra
environment above:

```yaml
# ~/.config/paddock/docker-compose.override.yml
volumes:
  agent_home:
    external: true
    name: agent-container_agent_home
```

```sh
docker compose -f src/paddock/image/docker-compose.yml \
  -f ~/.config/paddock/docker-compose.override.yml up -d
```

paddock now starts against the migrated volume instead of creating a fresh
`paddock_agent_home`. Don't bother doing the same for
`agent-container_ssh_host_keys`: host keys are cheap to regenerate (one
`StrictHostKeyChecking` prompt on your next connection) and paddock's
compose file already provisions its own `sshd_host_keys` volume, so nothing
is gained by carrying the old one forward.

Once you've confirmed paddock is up and reading from the migrated volume,
stop and remove the old stack:

```sh
docker compose -p agent-container down
```

**Do not add `-v` to that command.** `down -v` also deletes the stack's
volumes, including the `agent-container_agent_home` volume you just adopted.

If your `~/.ssh/config` has the line agent-container's README told you to
add — something like `Include ~/.config/agent-container/ssh_config` — remove
it or repoint it. paddock doesn't ship or generate an `ssh_config` file of
its own to include; connecting is your own business (see [SSH](#ssh)). A
leftover `Include` pointing at a file that no longer exists is a silent ssh
config error rather than a loud one, so replace it with a hand-written host
block instead:

```
Host paddock
  HostName localhost
  Port 2222
  User agent
  IdentityFile ~/.ssh/id_ed25519   # whatever key's public half is in ~/.config/paddock/authorized_keys
```

### From paddock 2.x

paddock 2.x built and ran a container imperatively, both named `paddock`,
backed by volumes `paddock_home` and `paddock_ssh_host_keys`. Those volumes
were never compose-managed, so they carry no compose labels — which is why
paddock's compose file deliberately names its own volumes `agent_home` and
`sshd_host_keys` rather than `home` and `ssh_host_keys`: the project-prefixed
names it creates (`paddock_agent_home`, `paddock_sshd_host_keys`) don't
collide with the 2.x ones. Had the names matched, compose would have refused
to start against them — it errors on a pre-existing volume that isn't
labeled as its own rather than silently adopting it, unless you mark it
`external: true`. So there's no override needed here: paddock starts clean
alongside the old volumes, and once you've salvaged anything worth keeping,
remove them directly:

```sh
docker rm -f paddock
docker volume rm paddock_home paddock_ssh_host_keys
```

**Both commands are destructive** — `docker rm -f` discards the container
(the image `paddock` is left behind; remove it separately with `docker rmi
paddock` if you want) and `docker volume rm` deletes the volume data for
good. Copy anything worth keeping out first, e.g.:

```sh
mkdir -p ~/paddock-home-backup
docker run --rm -v paddock_home:/old -v ~/paddock-home-backup:/backup \
  alpine cp -a /old/. /backup/
```

### Running both at once

If an old stack (either one) is still listening on port 2222 and you're not
ready to remove it yet, give paddock its own port for the transition:

```sh
PADDOCK_SSH_PORT=2223 paddock
```

or set it in `~/.config/paddock/.env` so it applies to every invocation
without having to repeat it.

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
