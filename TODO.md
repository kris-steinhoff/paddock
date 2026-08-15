# TODO

Remaining work after the paddock 3.0 compose rewrite landed on `main` (`9d18312`).

Beads was the tracker for this work, but its database migrated to schema v65 while the local binary only knows v53, so `bd` errors out on every command. This file is the interim record. The issue ids below are the original beads ids, kept so the two can be reconciled if beads comes back.

## Blocked on a real Docker daemon

None of the image work in the 3.0 rewrite was ever built. The dev container this repo is worked on from has no docker binary and no daemon socket, so every item here needs a run on the Colima host with the output brought back.

- **Verify the vendored image builds at all** (`paddock-aye.1`, deferred after 3 failed attempts). The Dockerfile was vendored from agent-container and reconciled by hand against paddock's own fixes. Nothing has confirmed it produces a working image. Acceptance: a clean-cache build succeeds with no config dir present, a build with a real `*.crt` in `~/.config/paddock/certs/` has `update-ca-certificates` report it added, and changing `PADDOCK_TOOLS_REFRESH` rebuilds only the layers below the gate.
- **Confirm the default CA build context resolves** (second half of `paddock-aye.5`). `src/paddock/image/ca-certificates/.gitkeep` is now tracked and verified present in the built wheel, which fixes the packaging half. The build half is unverified: no build has actually resolved `COPY --from=ca-certificates` against that directory.
- **Run the entrypoint verify scripts.** `scripts/verify-entrypoint.sh` needs a daemon and has never run. `scripts/verify-entrypoint-local.sh` does not need one and passes.
- **A real end to end pass** (`paddock-3t0.4`). Version bump and quality gates are done. Actually running `paddock build`, `up`, connecting, and `down` is not.
- **Retire the agent-container repo** (`paddock-3t0.5`, out of tree). Blocked until the vendored image is proven equivalent.

## Open work needing no Docker

- **Preflight checks** (`paddock-96h.6`). Right now a missing `docker` executable surfaces as a `ComposeError` from the first `compose.run` call. Decide whether to check `docker`, the compose plugin, and `authorized_keys` up front instead, and note that `authorized_keys` is the interesting one: `interpolation_env` always sets `PADDOCK_AUTHORIZED_KEYS` whether or not the file exists, so a missing file produces a container that starts fine and refuses every key rather than a clear failure.
- **`paddock init`** (`paddock-96h.8`, P3, optional). Scaffold the config directory.

## Small fixes found during integration

- **`--cached` help text is imprecise.** `cli.py` says it pins `PADDOCK_TOOLS_REFRESH` to 0. The implementation leaves the variable unset so the compose file's `${PADDOCK_TOOLS_REFRESH:-0}` default applies. Same result unless the user has exported the variable themselves, in which case it passes through.
- **`glab` install is slightly brittle.** The vendored block uses `grep -o '"tag_name":"[^"]*"' | cut`, which only matches compact JSON with no space after the colon, and it extracts the whole tarball rather than just the `bin/glab` member. Paddock's pre-vendoring copy used `grep -oP` and was more tolerant. This works against today's GitLab API. It was taken deliberately from agent-container, so changing it is a choice, not a bug fix.

## Repo housekeeping

- **No git tags exist.** Consider tagging `9d18312` as `v3.0`.
- **The `milhouse/*` branches are still around.** Their content reached `main` through curated commits rather than merges, so git's `--merged` only recognises three of them. The other five and their worktrees under `~/.herdr/worktrees/paddock/` can be deleted once nobody wants the history.
- **`.beads/interactions.jsonl` and `.beads/issues.jsonl` have uncommitted changes**, plus a stray untracked `.beads.gate.lock`. Left alone because beads was mid-migration and the exports may not be trustworthy.
- **Fix beads**: `CGO_ENABLED=0 go install -tags gms_pure_go github.com/steveyegge/beads/cmd/bd@latest`. Issues to close on the way back in: `paddock-dt1`, `paddock-3t0.1`, `paddock-3t0.2`, and the packaging half of `paddock-aye.5`.
