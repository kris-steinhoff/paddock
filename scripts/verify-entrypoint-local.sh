#!/usr/bin/env bash
# Smoke-tests the /etc/ssh volume workaround in src/paddock/image/entrypoint.sh
# (paddock-aye.3) WITHOUT a Docker daemon, by running the same sshd_config.d
# refresh and authorized_keys copy commands from entrypoint.sh against an
# isolated scratch tree and starting a real sshd against it.
#
# This is the fallback for hosts like paddock's own dev container, which has
# no docker/podman binary, no reachable daemon, and no unprivileged
# unshare(1) (so no mount-namespace or chroot isolation either) — see beads
# memory paddock-s-own-dev-container-is-where-this. scripts/verify-entrypoint.sh
# remains the higher-fidelity check (it runs the literal Dockerfile/compose
# build) and should be preferred on any host with a working Docker daemon.
#
# The scratch tree MUST live under $HOME, not /tmp: sshd's StrictModes checks
# every directory in the AuthorizedKeysFile path chain, and /tmp is
# world-writable, which StrictModes rejects outright.
#
# Checks all three acceptance criteria from paddock-aye.3, plus paddock-aye.4's:
#   1. sshd_config.d/paddock.conf is present and current after being seeded
#      with stale content (proves the "volume" content gets overwritten).
#   2. authorized_keys copied from a mount owned by an arbitrary uid lands as
#      agent:agent 0600.
#   3. A key listed in the config-dir authorized_keys can log in, and
#      password auth (disabled by paddock.conf) is refused.
#   4. (paddock-aye.4) sshd_config carries no PermitUserEnvironment line, and
#      root login (excluded by AllowUsers agent) is refused.
#
# Uses this host's own real openssh-server package/config as the stand-in for
# the image's (same Debian release), and this host's own "agent" user as the
# stand-in for the image's "agent" user — both already match in this
# environment. Runs sshd on a scratch port; never touches the real /etc/ssh.
#
# Usage: scripts/verify-entrypoint-local.sh [ssh-port]
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
paddock_sshd_config="$repo_root/src/paddock/image/sshd_config"
port="${1:-2299}"

if [ "$(id -un)" != agent ] || [ "$(id -u)" = 0 ]; then
    echo "This script assumes it's running as the non-root 'agent' user (matching" >&2
    echo "the image's runtime user); adjust before running as anyone else." >&2
    exit 1
fi

s="$(mktemp -d "$HOME/.paddock-verify-local-XXXXXX")"
chmod 700 "$s"
mkdir -p "$s"/etc/ssh/sshd_config.d "$s"/run/paddock "$s"/home_agent_ssh

sshd_pid=""
cleanup() {
    [ -n "$sshd_pid" ] && sudo kill "$sshd_pid" >/dev/null 2>&1 || true
    sudo rm -rf "$s"
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

echo "== setting up scratch sshd instance at $s =="
sudo ssh-keygen -A -f "$s" >/dev/null
sudo chown -R "$(id -un)":"$(id -gn)" "$s/etc"

{
    echo "Port $port"
    echo "ListenAddress 127.0.0.1"
    echo "HostKey $s/etc/ssh/ssh_host_ed25519_key"
    echo "HostKey $s/etc/ssh/ssh_host_rsa_key"
    echo "HostKey $s/etc/ssh/ssh_host_ecdsa_key"
    echo "PidFile $s/run/sshd.pid"
    echo "AuthorizedKeysFile $s/home_agent_ssh/authorized_keys"
    # Reuse this host's own stock sshd_config for its `Include` line and
    # defaults (same Debian package the image installs), redirected at the
    # scratch sshd_config.d instead of the real /etc/ssh/sshd_config.d.
    sed "s#/etc/ssh/sshd_config.d/\*.conf#$s/etc/ssh/sshd_config.d/*.conf#" /etc/ssh/sshd_config
} >"$s/etc/ssh/sshd_config"

echo "== criterion 4 (paddock-aye.4): sshd_config carries no PermitUserEnvironment =="
if grep -q PermitUserEnvironment "$paddock_sshd_config"; then
    bad "sshd_config still contains a PermitUserEnvironment line"
else
    ok "sshd_config contains no PermitUserEnvironment line"
fi

echo "== criterion 1: sshd_config.d/paddock.conf refresh over stale content =="
echo "STALE-FROM-PRIOR-IMAGE" >"$s/etc/ssh/sshd_config.d/paddock.conf"
# The exact refresh command from entrypoint.sh, paths substituted only.
mkdir -p -m 0755 "$s/etc/ssh/sshd_config.d"
cp "$paddock_sshd_config" "$s/etc/ssh/sshd_config.d/paddock.conf"
if diff -u "$paddock_sshd_config" "$s/etc/ssh/sshd_config.d/paddock.conf" >/dev/null; then
    ok "stale sshd_config.d/paddock.conf content was overwritten by the current image's config"
else
    bad "paddock.conf does not match the current image after the refresh"
fi

echo "== criterion 2: authorized_keys ownership/perms =="
ssh-keygen -t ed25519 -N '' -C paddock-verify -f "$s/id_ed25519" -q
cp "$s/id_ed25519.pub" "$s/run/paddock/authorized_keys"
# Simulate the read-only host mount owned by an arbitrary (non-agent) uid.
sudo chown 65534:65534 "$s/run/paddock/authorized_keys"
# The exact copy+chown+chmod sequence from entrypoint.sh, paths substituted only.
if [ -f "$s/run/paddock/authorized_keys" ]; then
    cp "$s/run/paddock/authorized_keys" "$s/home_agent_ssh/authorized_keys"
    sudo chown "$(id -un)":"$(id -gn)" "$s/home_agent_ssh/authorized_keys"
    chmod 600 "$s/home_agent_ssh/authorized_keys"
fi
stat_out="$(stat -c '%U:%G %a' "$s/home_agent_ssh/authorized_keys")"
if [ "$stat_out" = "$(id -un):$(id -gn) 600" ]; then
    ok "authorized_keys is $(id -un):$(id -gn) 0600 (was owned by uid 65534 in the source mount)"
else
    bad "authorized_keys is '$stat_out'"
fi

echo "== starting sshd on 127.0.0.1:$port =="
sudo /usr/sbin/sshd -D -e -f "$s/etc/ssh/sshd_config" >"$s/sshd.log" 2>&1 &
sshd_pid=$!
sleep 1
if ! kill -0 "$sshd_pid" 2>/dev/null; then
    bad "sshd failed to start"
    cat "$s/sshd.log"
    echo
    echo "$pass passed, $fail failed"
    exit 1
fi
ssh-keyscan -p "$port" 127.0.0.1 >"$s/known_hosts" 2>/dev/null

echo "== criterion 3: login with the config-dir authorized_keys =="
if login_out="$(ssh -i "$s/id_ed25519" -p "$port" \
    -o UserKnownHostsFile="$s/known_hosts" \
    -o BatchMode=yes \
    -o ConnectTimeout=10 \
    agent@127.0.0.1 'echo LOGIN_OK' 2>&1)" && [ "$login_out" = "LOGIN_OK" ]; then
    ok "ssh login succeeded with the config-dir authorized_keys"
else
    bad "ssh login failed: $login_out"
fi

echo "== bonus: password auth is refused (paddock.conf's PasswordAuthentication no) =="
neg_out="$(ssh -p "$port" -o UserKnownHostsFile="$s/known_hosts" -o BatchMode=yes \
    -o PreferredAuthentications=password -o ConnectTimeout=10 \
    agent@127.0.0.1 'echo SHOULD_NOT_HAPPEN' 2>&1 || true)"
if echo "$neg_out" | grep -qi "permission denied"; then
    ok "password auth is refused"
else
    bad "password auth was not refused: $neg_out"
fi

echo "== criterion 4 (paddock-aye.4): root login is refused =="
root_out="$(ssh -i "$s/id_ed25519" -p "$port" \
    -o UserKnownHostsFile="$s/known_hosts" \
    -o BatchMode=yes \
    -o ConnectTimeout=10 \
    root@127.0.0.1 'echo SHOULD_NOT_HAPPEN' 2>&1 || true)"
if echo "$root_out" | grep -qi "permission denied"; then
    ok "root login is refused (AllowUsers agent excludes root)"
else
    bad "root login was not refused: $root_out"
fi

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
