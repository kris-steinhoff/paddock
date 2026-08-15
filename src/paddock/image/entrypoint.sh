#!/bin/sh
set -eu

# The image's USER is agent, so that `docker exec` lands there rather than
# giving a root shell in the persistent /home/agent volume. Everything below
# still needs root, so it goes through sudo (agent has NOPASSWD:ALL). Resolve
# that once here rather than hardcoding sudo, so the entrypoint still works if
# the container is run as root, e.g. with a `user:` override.
SUDO=""
[ "$(id -u)" -eq 0 ] || SUDO="sudo"

# No systemd/tmpfiles in the container to create sshd's privilege-separation
# dir, and no init script to generate host keys on first boot, so do both.
$SUDO mkdir -p -m 0755 /run/sshd
$SUDO ssh-keygen -A >/dev/null

# /etc/ssh is the paddock_ssh_host_keys volume, so a stale copy from before
# an image rebuild would otherwise shadow the image's sshd_config.d/paddock.conf
# forever. Refresh it into place on every start instead.
$SUDO mkdir -p -m 0755 /etc/ssh/sshd_config.d
$SUDO cp /etc/paddock/sshd_config /etc/ssh/sshd_config.d/paddock.conf

# The authorized_keys source is a read-only mount owned by whatever UID it
# has on the host, which fails sshd's StrictModes check. Copy it in and fix
# ownership/perms on every start instead of mounting straight into ~/.ssh.
if [ -f /run/paddock/authorized_keys ]; then
    $SUDO cp /run/paddock/authorized_keys /home/agent/.ssh/authorized_keys
    $SUDO chown agent:agent /home/agent/.ssh/authorized_keys
    $SUDO chmod 600 /home/agent/.ssh/authorized_keys
fi

# sshd must be root to bind :22 and do privilege separation. Exec so it takes
# over PID 1's child slot and tini's signal forwarding reaches it.
exec $SUDO /usr/sbin/sshd -D -e
