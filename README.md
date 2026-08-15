# paddock

Build and run a single general-purpose development container via
[docker compose](https://docs.docker.com/compose/), and nothing else. One
Dockerfile and one compose file ship baked into the paddock package itself,
so there's no per-repo image or config tree to author. paddock's whole job
is to assemble the right `docker compose` invocation (packaged base file,
your optional per-machine override, the `PADDOCK_*` interpolation
variables) and get out of the way.

paddock does not attach you to the container. Connecting is your own
business. The image ships [herdr](https://herdr.dev) and `sshd`, so
`herdr --remote ssh://agent@localhost:2222` is the intended path, but
paddock never runs it, generates no keys, and does not touch your ssh
config.

Ships: `claude`, `codex`, `copilot`, `opencode`, `herdr`, `bd`, `neovim`,
`gh`, `glab`, `terraform`, `uv`, `chezmoi`, `starship`, `typos`,
`pre-commit`, and `sshd`, on top of a `node:24-trixie-slim` base with the
usual shell tooling (`zsh`, `ripgrep`, `fd`, `bat`, `eza`, `fzf`, `jq`,
`direnv`, `git`, `python3`).

## Install

Install it as a tool with [uv](https://docs.astral.sh/uv/):

```sh
uv tool install git+https://github.com/kris-steinhoff/paddock
paddock --help
```

Requires `docker` with the `compose` plugin (`docker compose version`
should work) on `PATH`. paddock shells out to `docker compose` directly and
doesn't vendor or install docker itself. Nothing is checked up front: a
missing `docker` surfaces as `error: docker executable not found on PATH`
from the first command that needs it.

## Usage

paddock wraps no compose verb. Everything after `--` goes to
`docker compose` untouched:

```sh
paddock -- build                # build the image
paddock -- up -d                # start the container in the background
paddock -- down                 # stop and remove the container
paddock -- down -v              # ...and delete the volumes (see Persistence)
paddock -- ps                   # container status, including the published ports
paddock -- logs -f              # follow the logs
paddock -- exec agent zsh       # a shell in the container
paddock -- config               # the fully resolved compose config
paddock -- --help               # docker compose's own help
```

paddock supplies only the `-f`/`--env-file` assembly (packaged base compose
file, your optional override, your optional `.env`) and the `PADDOCK_*`
interpolation variables, then execs compose. Since it execs, compose's exit
code and error messages reach you unmediated. Every compose subcommand is
available without hand-assembling the file list, and there's nothing for
paddock to keep in sync as compose grows new ones.

paddock's own flags go *before* the `--`:

```sh
paddock --init                  # scaffold the config directory
paddock --no-refresh -- build   # build reusing the cached tool-install layer
paddock --version
paddock --help                  # paddock's help, as opposed to `paddock -- --help`
```

**The `--` is required.** `paddock up` is an error, not a shortcut for
`paddock -- up`, so that paddock's flags and compose's can never be
confused for one another. Bare `paddock` prints help and exits 0.

## Connecting

Once `paddock -- up -d` is running, connect however you like. The intended
path is [herdr](https://herdr.dev), which the image ships:

```sh
herdr --remote ssh://agent@localhost:2222
```

Plain `ssh agent@localhost -p 2222` works the same way, as does anything
else that speaks ssh. The container's sshd allows only the `agent` user and
only public-key auth (no passwords, no root login), and the port is
published on `127.0.0.1` only. If you've changed the port, `paddock -- ps`
shows the mapping it resolved.

For a shell without ssh at all:

```sh
paddock -- exec agent zsh
```

## Configuration

Everything lives under `${XDG_CONFIG_HOME:-~/.config}/paddock`.
`paddock --init` creates that directory and `certs/` inside it; every file
in it is optional to paddock, but without `authorized_keys` you can't ssh
in:

- **`authorized_keys`**: public keys allowed to ssh in, in standard
  `authorized_keys` format. paddock always sets `PADDOCK_AUTHORIZED_KEYS`
  to this path and the compose file mounts it read-only into the container,
  where the entrypoint copies it to `/home/agent/.ssh/authorized_keys` with
  the ownership and mode sshd's `StrictModes` demands. paddock prints a
  warning on any passthrough if the file doesn't exist, since compose
  itself doesn't treat a missing file as an error: the container starts
  fine and just refuses every key. Populate it the normal way, or pull the
  public half straight out of your ssh-agent:

  ```sh
  ssh-add -L >> ~/.config/paddock/authorized_keys
  ```

- **`certs/*.crt`**: root CA certificates to trust in the image (e.g. a
  corporate TLS-intercepting proxy). Any `*.crt` file here makes paddock
  point `PADDOCK_CA_CONTEXT` at this directory for the build. With none
  present the variable is left unset and the compose file falls back to the
  empty `ca-certificates/` directory packaged alongside it, so the build
  never fails for lack of a source. See [Corporate CA
  certificates](#corporate-ca-certificates).

- **`docker-compose.override.yml`**: a per-machine compose file layered on
  top of the packaged one with a second `-f`, so its values win. This is
  where bind mounts, extra published ports, and extra container environment
  go, since the packaged compose file is read-only inside site-packages.

  ```yaml
  # ~/.config/paddock/docker-compose.override.yml
  services:
    agent:
      volumes:
        - ~/code/github.com/kris-steinhoff/some-project:/home/agent/workspace/some-project
      environment:
        - EXTRA_TOKEN
  ```

- **`.env`**: passed to `docker compose` as `--env-file` when present, for
  setting the `PADDOCK_*` interpolation variables below without exporting
  them in every shell. It feeds interpolation only (see [Env vars and
  secrets](#env-vars-and-secrets)).

## PADDOCK_* variables

The packaged compose file reads these for interpolation, i.e. the
`${VAR:-default}` substitutions inside the file. All of them can be set in
your shell or in the config dir's `.env`. paddock sets only the ones marked
below, and never overwrites a value you set yourself.

| Variable | Default | Used for | Set by paddock? |
| --- | --- | --- | --- |
| `PADDOCK_SSH_PORT` | `2222` | published host ssh port (bound to `127.0.0.1`) | no, pass-through only |
| `PADDOCK_HTTP_PORT` | `8000` | published host http port (bound to `127.0.0.1`) | no, pass-through only |
| `PADDOCK_AUTHORIZED_KEYS` | none | mounted read-only as the container's `authorized_keys` source | yes, always |
| `PADDOCK_CA_CONTEXT` | `./ca-certificates` (packaged empty dir) | the `ca-certificates` named build context | yes, when `certs/` holds at least one `*.crt` |
| `PADDOCK_TOOLS_REFRESH` | `0` | the Dockerfile's `TOOLS_REFRESH` cache gate | yes, on every invocation unless `--no-refresh` |

Since paddock no longer knows which compose verb you're running, it sets a
fresh `PADDOCK_TOOLS_REFRESH` timestamp on *every* invocation rather than
guessing at which ones are builds. That only changes what a build does, but
compose folds build args into the config hash it stamps on the container,
so a plain `paddock -- up` may recreate the container rather than reusing
it. Both named volumes survive that (see [Persistence](#persistence)), so
the cost is a few seconds and any in-container process state. Use
`paddock --no-refresh -- up` to avoid it.

## Env vars and secrets

paddock resolves no secrets on your behalf. There is no `settings.yaml`,
and no `{command: ...}` indirection like paddock 2.x had. An environment
variable can reach the container from exactly three places:

1. **Your shell**, for anything that shouldn't touch disk:

   ```sh
   GITHUB_TOKEN=$(op read op://Private/GitHub/token) paddock -- up -d
   ```

   The packaged compose file lists a few valueless pass-through entries
   (`GITHUB_TOKEN`, `GITLAB_TOKEN`, `ANTHROPIC_API_KEY`) that pick up
   whatever is in your environment when paddock runs compose.

2. **`docker-compose.override.yml`**, for any other variable name. Add it
   as a pass-through entry the same way the packaged file does, then run
   `EXTRA_TOKEN=... paddock -- up -d`, or give it a literal value in the override
   if you don't mind it on disk.

3. **A tool's own login inside the container**, e.g. `gh auth login` or
   `claude`. That state lands in `/home/agent` and persists in the
   `agent_home` volume, so it survives restarts and rebuilds.

**`--env-file` is not the fourth place.** `docker compose --env-file`
(which paddock passes whenever the config dir's `.env` exists) feeds
compose *interpolation* only, meaning the `${VAR:-default}` substitutions
inside the compose file itself, like the ports and `PADDOCK_TOOLS_REFRESH`
above. It cannot inject an arbitrary variable into the container. Container
environment comes only from the compose file's `environment:`/`env_file:`
keys, which is why route 2 needs an override entry rather than a new line
in `.env`.

## Persistence

Two named docker volumes, both prefixed by the compose project name
(`name: paddock` in the packaged file):

- `paddock_agent_home` maps to `/home/agent`: dotfiles, shell history, tool
  auth (`claude`, `gh`, and friends).
- `paddock_sshd_host_keys` maps to `/etc/ssh`: sshd's host keys, so
  rebuilding the image doesn't change the container's host key and trip
  `StrictHostKeyChecking`.

Both survive `stop`, `start`, `restart`, a plain `down`, and a rebuild.
**`paddock -- down -v` is the destructive one.** It deletes both volumes
for good, tool auth and shell history included.

## The tools cache gate

The Dockerfile is split by a cache gate. Everything above it (apt packages,
`gh`, `glab`, `terraform`, `neovim`, `chezmoi`, `starship`, `opencode`, the
dotfiles bootstrap with its expensive nvim plugin pre-fetch) stays cached
across rebuilds. Everything below it (`herdr`, `claude`, `copilot`,
`codex`, `bd`) reinstalls whenever the `TOOLS_REFRESH` build arg changes,
so those fast-moving tools don't silently pin an old version forever.

- paddock sets a fresh `PADDOCK_TOOLS_REFRESH` timestamp by default,
  busting the gate so those tools reinstall latest on the next build.
- `paddock --no-refresh -- build` leaves the variable alone instead, so the
  compose file's default of `0` applies and the cached layers are reused.

`paddock -- build --no-cache` is the unrelated bigger hammer: `--no-cache`
goes straight to `docker compose build` and rebuilds every layer.

## Corporate CA certificates

Drop the root CA(s) into `~/.config/paddock/certs/` as `*.crt` files and
run `paddock -- build`. paddock points the `ca-certificates` build context at
that directory, and the Dockerfile copies its contents into
`/usr/local/share/ca-certificates/paddock/` and runs
`update-ca-certificates` right after the base image's first `apt-get
install`, which is what provides that tooling in the first place. That one
step is unavoidably not covered, so it has to reach the network without the
corporate CA already trusted. Every other networked step (curl, npm,
further apt) runs after the trust is in place.

Node-based tools (`claude`, `opencode`, `npm`) and some Python tooling
ignore the system trust store by default, so the image also pins
`NODE_EXTRA_CA_CERTS`, `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`,
`CURL_CA_BUNDLE`, `PIP_CERT`, and `GIT_SSL_CAINFO` at the merged system
bundle. The trust is baked into the image, so it covers the running
container too with no runtime mount, and changing the certs needs a
`paddock -- build` to take effect.

This covers CA trust only. If your network also needs an
`HTTP_PROXY`/`HTTPS_PROXY` to reach anything *during the build itself*,
that isn't wired up.

## Migrating from an older setup

paddock has gone through two earlier shapes: agent-container (a separate,
per-repo compose project) and paddock 2.x (this same project, but driving
`docker build`/`docker run` directly instead of compose). Both left behind
a container, an image, and, the part worth being careful with, a home
volume full of tool auth and shell history. The risk in either migration is
losing that volume by forgetting about it.

### From agent-container

agent-container's compose project was named `agent-container`, so its
volumes are `agent-container_agent_home` and `agent-container_ssh_host_keys`.
Reuse the home volume instead of starting paddock with an empty one, by
declaring paddock's own `agent_home` volume as external and pointing it at
the old name, in the same override file used for bind mounts and extra
environment above:

```yaml
# ~/.config/paddock/docker-compose.override.yml
volumes:
  agent_home:
    external: true
    name: agent-container_agent_home
```

```sh
paddock -- up -d
```

paddock now starts against the migrated volume instead of creating a fresh
`paddock_agent_home`. Don't bother doing the same for
`agent-container_ssh_host_keys`. Host keys are cheap to regenerate (one
`StrictHostKeyChecking` prompt on your next connection) and paddock's
compose file already provisions its own `sshd_host_keys` volume, so nothing
is gained by carrying the old one forward.

Once you've confirmed paddock is up and reading from the migrated volume,
stop and remove the old stack:

```sh
docker compose -p agent-container down
```

**Do not add `-v` to that command.** `down -v` also deletes the stack's
volumes, including the `agent-container_agent_home` volume you just
adopted.

If your `~/.ssh/config` has the line agent-container's README told you to
add, something like `Include ~/.config/agent-container/ssh_config`, remove
it or repoint it. paddock ships and generates no `ssh_config` of its own to
include, since connecting is your own business (see
[Connecting](#connecting)). A leftover `Include` pointing at a file that no
longer exists is a silent ssh config error rather than a loud one, so
replace it with a hand-written host block instead:

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
were never compose-managed, so they carry no compose labels, which is why
paddock's compose file deliberately names its own volumes `agent_home` and
`sshd_host_keys` rather than `home` and `ssh_host_keys`: the
project-prefixed names it creates (`paddock_agent_home`,
`paddock_sshd_host_keys`) don't collide with the 2.x ones. Had the names
matched, compose would have refused to start against them, since it errors
on a pre-existing volume that isn't labeled as its own rather than silently
adopting it, unless you mark it `external: true`. So there's no override
needed here. paddock starts clean alongside the old volumes, and once
you've salvaged anything worth keeping, remove them directly:

```sh
docker rm -f paddock
docker volume rm paddock_home paddock_ssh_host_keys
```

**Both commands are destructive.** `docker rm -f` discards the container
(the image `paddock` is left behind, remove it separately with `docker rmi
paddock` if you want) and `docker volume rm` deletes the volume data for
good. Copy anything worth keeping out first, e.g.:

```sh
mkdir -p ~/paddock-home-backup
docker run --rm -v paddock_home:/old -v ~/paddock-home-backup:/backup \
  alpine cp -a /old/. /backup/
```

Paddock 2.x's `settings.yaml` has no equivalent. Environment values move to
your shell or an override file (see [Env vars and
secrets](#env-vars-and-secrets)), and `ca_certificates:` entries become
`*.crt` files in `~/.config/paddock/certs/`.

### Running both at once

If an old stack (either one) is still listening on port 2222 and you're not
ready to remove it yet, give paddock its own port for the transition:

```sh
PADDOCK_SSH_PORT=2223 paddock -- up -d
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

`pytest` covers pure logic only (argv and interpolation-env assembly, path
helpers, CLI wiring) and never talks to a docker daemon. Two scripts cover
the container side, both smoke tests of the entrypoint's `/etc/ssh`
named-volume workaround (a stale volume must not shadow the image's
`sshd_config.d/paddock.conf`, and `authorized_keys` must land as
`agent:agent 0600`):

```sh
scripts/verify-entrypoint.sh [ssh-port]        # needs a real Docker daemon
scripts/verify-entrypoint-local.sh [ssh-port]  # no daemon needed
```

`verify-entrypoint.sh` runs the literal Dockerfile and compose build in an
isolated compose project and image tag, so it never touches a real
`paddock` container, image, or volume. It's the higher-fidelity check and
the one to prefer on any host that can reach a daemon.
`verify-entrypoint-local.sh` is the fallback for hosts without one (paddock's
own dev container included): it replays the entrypoint's copy commands
against a scratch tree and starts a real sshd against it.
