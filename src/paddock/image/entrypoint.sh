#!/bin/sh
set -eu

# No systemd/tmpfiles in the container to create sshd's privilege-separation
# dir, and no init script to generate host keys on first boot, so do both.
mkdir -p -m 0755 /run/sshd
ssh-keygen -A >/dev/null

# /etc/ssh is the paddock_ssh_host_keys volume, so a stale copy from before
# an image rebuild would otherwise shadow the image's sshd_config.d/paddock.conf
# forever. Refresh it into place on every start instead.
mkdir -p -m 0755 /etc/ssh/sshd_config.d
cp /etc/paddock/sshd_config /etc/ssh/sshd_config.d/paddock.conf

# The authorized_keys source is a read-only mount owned by whatever UID it
# has on the host, which fails sshd's StrictModes check. Copy it in and fix
# ownership/perms on every start instead of mounting straight into ~/.ssh.
if [ -f /run/paddock/authorized_keys ]; then
    cp /run/paddock/authorized_keys /home/agent/.ssh/authorized_keys
    chown agent:agent /home/agent/.ssh/authorized_keys
    chmod 600 /home/agent/.ssh/authorized_keys
fi

exec /usr/sbin/sshd -D -e
