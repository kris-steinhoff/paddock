#!/usr/bin/env bash
# Smoke-tests the /etc/ssh volume workaround in src/paddock/image/entrypoint.sh
# (paddock-aye.3) against a real Docker daemon. paddock's own dev container has
# no Docker daemon access, so this can't run there — run it on a host that can
# reach one (e.g. the Colima host on macOS) with `docker compose` (v2) on PATH.
#
# Checks:
#   1. sshd_config.d/paddock.conf is present and current after an image
#      rebuild against a pre-existing sshd_host_keys volume seeded with a
#      stale config (proves the volume's stale content doesn't shadow it).
#   2. authorized_keys lands as agent:agent 0600.
#   3. A key listed in the config-dir authorized_keys can log in.
#   4. `docker compose exec` lands as agent, not root. The image's USER is
#      agent so an exec'd shell can't write root-owned files into the
#      persistent /home/agent volume.
#   5. SIGTERM still reaches sshd, which the entrypoint's sudo hop could
#      break: a container that ignores it sits out the full stop timeout
#      before being SIGKILLed.
#
# Everything is scoped to an isolated compose project ("paddock-verify") and
# an isolated image tag, so it never touches a real `paddock` container,
# image, or volumes on the same host.
#
# Usage: scripts/verify-entrypoint.sh [ssh-port]
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_file="$repo_root/src/paddock/image/docker-compose.yml"
project="paddock-verify"
image_tag="paddock-verify-entrypoint"
port="${1:-2299}"

# Under $HOME, not the system tmpdir: on VM-backed Docker setups (Colima and
# similar), only specific host paths are shared into the VM, and $HOME is
# reliably one of them while /tmp or /var/folders (macOS's default mktemp
# location) may not be. A bind-mount source outside the shared paths mounts
# as silently empty rather than erroring, which broke criterion 2 below.
workdir="$(mktemp -d "$HOME/.paddock-verify.XXXXXX")"
override_file="$workdir/docker-compose.override.yml"
cat >"$override_file" <<EOF
services:
  agent:
    image: ${image_tag}
EOF

compose() {
    docker compose -p "$project" -f "$compose_file" -f "$override_file" "$@"
}

cleanup() {
    compose down --volumes --remove-orphans >/dev/null 2>&1 || true
    docker rmi "$image_tag" >/dev/null 2>&1 || true
    rm -rf "$workdir"
}
trap cleanup EXIT

pass=0
fail=0
ok() {
    echo "PASS: $1"
    pass=$((pass + 1))
}
bad() {
    echo "FAIL: $1"
    fail=$((fail + 1))
}

ssh-keygen -t ed25519 -N '' -C paddock-verify -f "$workdir/id_ed25519" -q
authorized_keys="$workdir/authorized_keys"
cp "$workdir/id_ed25519.pub" "$authorized_keys"

export PADDOCK_AUTHORIZED_KEYS="$authorized_keys"
export PADDOCK_SSH_PORT="$port"

echo "== building image =="
compose build

echo "== creating services (without starting) =="
compose create

# Seed the sshd_host_keys volume with a stale config from a "previous image",
# the same way an existing container's volume would look before a rebuild.
sshd_vol="$(docker volume ls \
    --filter "label=com.docker.compose.project=$project" \
    --filter "label=com.docker.compose.volume=sshd_host_keys" \
    --format '{{.Name}}')"
if [ -z "$sshd_vol" ]; then
    echo "FAIL: could not resolve the sshd_host_keys volume name" >&2
    exit 1
fi
docker run --rm -v "$sshd_vol":/etc/ssh alpine sh -c \
    'mkdir -p /etc/ssh/sshd_config.d && printf "STALE-FROM-PRIOR-IMAGE\n" > /etc/ssh/sshd_config.d/paddock.conf'

echo "== starting =="
compose start

echo "== waiting for sshd to accept connections on 127.0.0.1:$port =="
ready=0
for _ in $(seq 1 30); do
    if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
        exec 3>&- 3<&-
        ready=1
        break
    fi
    sleep 1
done
if [ "$ready" != 1 ]; then
    bad "sshd never came up on 127.0.0.1:$port"
    echo "== container logs =="
    compose logs agent || true
    exit 1
fi

echo "== criterion 1: sshd_config.d/paddock.conf present and current =="
if compose exec -T agent sh -c \
    'diff -u /etc/paddock/sshd_config /etc/ssh/sshd_config.d/paddock.conf'; then
    ok "sshd_config.d/paddock.conf matches the image's /etc/paddock/sshd_config (stale volume content was overwritten)"
else
    bad "sshd_config.d/paddock.conf does not match the current image (stale volume content was not refreshed)"
fi

echo "== criterion 2: authorized_keys ownership/perms =="
if stat_out="$(compose exec -T agent stat -c '%U:%G %a' /home/agent/.ssh/authorized_keys 2>&1)"; then
    if [ "$stat_out" = "agent:agent 600" ]; then
        ok "authorized_keys is agent:agent 0600"
    else
        bad "authorized_keys is '$stat_out', expected 'agent:agent 600'"
    fi
else
    bad "authorized_keys stat failed: $stat_out"
fi

echo "== criterion 3: login with the config-dir authorized_keys =="
if login_out="$(ssh -i "$workdir/id_ed25519" \
    -p "$port" \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o BatchMode=yes \
    -o ConnectTimeout=10 \
    -o LogLevel=ERROR \
    agent@127.0.0.1 'echo LOGIN_OK' 2>&1)" && [ "$login_out" = "LOGIN_OK" ]; then
    ok "ssh login succeeded with the mounted authorized_keys"
else
    bad "ssh login failed: $login_out"
fi

echo "== criterion 4: compose exec lands as agent, not root =="
if exec_user="$(compose exec -T agent id -un 2>&1)"; then
    if [ "$exec_user" = agent ]; then
        ok "compose exec runs as agent (no root-owned writes into /home/agent)"
    else
        bad "compose exec runs as '$exec_user', expected 'agent'"
    fi
else
    bad "could not resolve the compose exec user: $exec_user"
fi

# Last, since it stops the container. The entrypoint runs as agent and reaches
# sshd through `sudo`, so this is where a broken signal chain would show up:
# sshd never sees SIGTERM and compose waits out the full timeout, then SIGKILLs.
echo "== criterion 5: SIGTERM reaches sshd through tini and sudo =="
stop_started=$(date +%s)
compose stop -t 10 >/dev/null 2>&1 || true
stop_elapsed=$(($(date +%s) - stop_started))
if [ "$stop_elapsed" -lt 8 ]; then
    ok "container stopped in ${stop_elapsed}s (SIGTERM propagated to sshd)"
else
    bad "container took ${stop_elapsed}s to stop; SIGTERM likely never reached sshd"
fi

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
