FROM node:24-trixie-slim

# ca-certificates (and so update-ca-certificates) isn't in the base image;
# apt-get itself needs it before trusting any extra CA below, so this has to
# be its own step ahead of the corporate-CA block, not folded into it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        ca-certificates \
        curl \
        openssh-server \
        sudo \
        zsh \
        direnv \
        ripgrep \
        fd-find \
        bat \
        eza \
        fzf \
        jq \
        less \
        unzip \
        xz-utils \
        build-essential \
        bubblewrap \
        python3 \
        python3-venv \
        python3-pip \
        locales \
        tini \
    && rm -rf /var/lib/apt/lists/* \
    && sed -i '/en_US.UTF-8/s/^# //' /etc/locale.gen && locale-gen \
    && ln -sf /usr/bin/fdfind /usr/local/bin/fd \
    && ln -sf /usr/bin/batcat /usr/local/bin/bat

ENV LANG=en_US.UTF-8

# Trust any extra CA(s) (e.g. a corporate TLS-intercepting proxy) before any
# other networked step below. ca-certificates is a named build context (see
# docker-compose.yml's additional_contexts), defaulting to a ./ca-certificates
# dir shipped empty in the package, so this COPY never fails for lack of a
# source.
COPY --from=ca-certificates . /usr/local/share/ca-certificates/paddock/
RUN update-ca-certificates
# System trust store covers apt/curl/git/gh/glab/uv, but Node (and so npm,
# claude, opencode) and some Python tooling ship their own bundles and ignore
# it unless told to via these env vars.
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    GIT_SSL_CAINFO=/etc/ssl/certs/ca-certificates.crt

# Debian's apt doesn't carry gh; pull from GitHub's own apt repo per its
# official install docs (https://github.com/cli/cli/blob/trunk/docs/install_linux.md).
RUN mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# GitLab's glab isn't in Debian/apt either. It ships pre-built release tarballs
# on gitlab.com; resolve the latest tag via the API and pull the matching arch
# binary (bin/glab inside the tarball). uname -m for the same reason as nvim below.
RUN arch=$(case "$(uname -m)" in aarch64) echo arm64 ;; *) echo amd64 ;; esac) \
    && tag=$(curl -fsSL "https://gitlab.com/api/v4/projects/gitlab-org%2Fcli/releases/permalink/latest" | grep -o '"tag_name":"[^"]*"' | head -1 | cut -d'"' -f4) \
    && ver=${tag#v} \
    && curl -fsSLo /tmp/glab.tar.gz "https://gitlab.com/gitlab-org/cli/-/releases/${tag}/downloads/glab_${ver}_linux_${arch}.tar.gz" \
    && tar -C /tmp -xzf /tmp/glab.tar.gz \
    && mv /tmp/bin/glab /usr/local/bin/glab \
    && rm -rf /tmp/glab.tar.gz /tmp/bin

# Terraform isn't in Debian/apt, and HashiCorp's apt repo doesn't reliably carry
# a trixie release. HashiCorp ships per-version zip binaries; resolve the latest
# stable via the checkpoint API and pull the matching arch (single `terraform`
# binary inside the zip). uname -m for the same reason as nvim below.
RUN arch=$(case "$(uname -m)" in aarch64) echo arm64 ;; *) echo amd64 ;; esac) \
    && ver=$(curl -fsSL https://checkpoint-api.hashicorp.com/v1/check/terraform | grep -o '"current_version":"[^"]*"' | head -1 | cut -d'"' -f4) \
    && curl -fsSLo /tmp/terraform.zip "https://releases.hashicorp.com/terraform/${ver}/terraform_${ver}_linux_${arch}.zip" \
    && unzip -d /usr/local/bin /tmp/terraform.zip \
    && rm /tmp/terraform.zip

# typos-cli isn't in Debian/apt either. It ships prebuilt musl tarballs on
# GitHub releases (bin/typos inside); resolve the latest tag via the API and
# pull the matching arch. uname -m for the same reason as nvim below.
# GitHub's API 403s requests with no User-Agent header, which curl doesn't
# send by default.
RUN arch=$(case "$(uname -m)" in aarch64) echo aarch64 ;; *) echo x86_64 ;; esac) \
    && tag=$(curl -fsSL -H "User-Agent: paddock" https://api.github.com/repos/crate-ci/typos/releases/latest | grep -o '"tag_name":"[^"]*"' | head -1 | cut -d'"' -f4) \
    && curl -fsSLo /tmp/typos.tar.gz "https://github.com/crate-ci/typos/releases/download/${tag}/typos-${tag}-${arch}-unknown-linux-musl.tar.gz" \
    && mkdir -p /tmp/typos \
    && tar -C /tmp/typos -xzf /tmp/typos.tar.gz \
    && mv /tmp/typos/typos /usr/local/bin/typos \
    && rm -rf /tmp/typos.tar.gz /tmp/typos

# Neovim's Debian/apt build lags releases by a lot; the dotfiles' lazy-lock.json
# and treesitter setup expect a current release, so pull the GitHub binary.
# uname -m (not TARGETARCH) since that ARG only gets auto-populated by
# BuildKit — silently empty otherwise, defaulting to the wrong arch.
RUN arch=$(case "$(uname -m)" in aarch64) echo arm64 ;; *) echo x86_64 ;; esac) \
    && curl -fsSLo /tmp/nvim.tar.gz "https://github.com/neovim/neovim/releases/latest/download/nvim-linux-${arch}.tar.gz" \
    && tar -C /opt -xzf /tmp/nvim.tar.gz \
    && mv /opt/nvim-linux-${arch} /opt/nvim \
    && ln -s /opt/nvim/bin/nvim /usr/local/bin/nvim \
    && rm /tmp/nvim.tar.gz

RUN BINDIR=/usr/local/bin sh -c "$(curl -fsLS get.chezmoi.io)"

RUN curl -fsSL https://starship.rs/install.sh | sh -s -- --yes

# Debian's system pip refuses installs outside a venv (PEP 668); pre-commit
# is a global CLI tool here, not a project dependency, so override that.
RUN pip3 install --break-system-packages pre-commit

# Cached tools: kept above the cache gate near the bottom. The fast-moving
# ones (claude, copilot, codex) install below the gate so they track latest.
RUN npm install -g opencode-ai tree-sitter-cli \
    && npm cache clean --force

RUN useradd -m -s /usr/bin/zsh agent \
    && echo 'agent ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/agent \
    && mkdir -p /home/agent/.ssh \
    && chmod 700 /home/agent/.ssh \
    && chown -R agent:agent /home/agent/.ssh

# Baked outside /etc/ssh, not straight into sshd_config.d: /etc/ssh is the
# paddock_ssh_host_keys volume (so host keys survive container recreation),
# and Docker only seeds a named volume from the image on its *first* use —
# once created, the volume's own content always wins over the image, so a
# later image rebuild would silently never reach a config file placed
# directly under /etc/ssh. entrypoint.sh copies it into place on every start
# instead, the same way it handles authorized_keys below.
COPY sshd_config /etc/paddock/sshd_config
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 755 /usr/local/bin/entrypoint.sh

# chezmoi apply runs run_once_bootstrap.sh (which skips the brew step here
# since brew isn't installed) to lay down dotfiles and pre-fetch the pinned
# nvim plugins. Kept above the cache gate so that expensive plugin pre-fetch
# stays cached. It lays down herdr's config too; herdr itself installs below
# the gate and doesn't need to exist yet for the config to be written.
USER agent
WORKDIR /home/agent
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/home/agent/.local/bin:${PATH}"
# Debian's zsh package seeds a skeleton ~/.zshrc via /etc/skel, which makes
# run_once_bootstrap.sh think there's an existing config to merge and prompt
# interactively (with no stdin, that prompt aborts the build). Remove it first.
RUN rm -f /home/agent/.zshrc
RUN chezmoi init --apply kris-steinhoff/dotfiles

# ---------------------------------------------------------------------------
# Cache gate. Everything ABOVE stays cached across rebuilds; everything BELOW
# reinstalls whenever the TOOLS_REFRESH build arg changes. Docker only
# cache-misses an ARG on its first *use* (not its declaration), so the echo
# below is the real gate — it and every layer under it rebuild when the value
# changes. docker-compose.yml forwards PADDOCK_TOOLS_REFRESH here, which
# paddock sets to a fresh timestamp on `paddock build` / `paddock up --build`
# so these fast-moving tools track latest; left unset it defaults to 0 and
# the cached layers are reused (`--cached` pins it that way).
# ---------------------------------------------------------------------------
ARG TOOLS_REFRESH=0
RUN echo "tools refresh token: ${TOOLS_REFRESH}"

# herdr installs into the invoking user's home dir.
RUN curl -fsSL https://herdr.dev/install.sh | sh

USER root
# Claude Code's CLI is a platform-native binary that the npm package's
# postinstall fetches separately. That fetch doesn't land under `npm install
# -g` here (npm skips the optional platform-specific dependency), so `claude`
# errors with "native binary not installed". Running install.cjs explicitly
# pulls the binary into the package tree under /usr/local — which, unlike
# /home/agent, isn't masked by the persistent agent_home volume at runtime.
RUN npm install -g @anthropic-ai/claude-code @github/copilot @openai/codex \
    && node "$(npm root -g)/@anthropic-ai/claude-code/install.cjs" \
    && npm cache clean --force

# Beads (bd): AI-supervised issue tracker CLI. No apt/npm package; the
# installer resolves the latest release itself, so keep it below the cache
# gate to track new versions. It installs to /usr/local/bin since that's
# root-writable here.
RUN curl -fsSL https://raw.githubusercontent.com/gastownhall/beads/main/scripts/install.sh | bash

# Land on agent, not root. `docker exec` (and so `paddock -- exec agent zsh`)
# uses the image's USER, and a root shell in /home/agent quietly writes
# root-owned files into the persistent agent_home volume, which the agent user
# then can't overwrite. sshd is unaffected either way, since it drops to agent
# on login. The privileged setup sshd needs (/run/sshd, ssh-keygen -A into the
# /etc/ssh volume, chowning authorized_keys, binding port 22) is why
# entrypoint.sh sudos those steps rather than this staying USER root.
USER agent

EXPOSE 22
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
