# TODO

Remaining work after the paddock 3.0 compose rewrite landed on `main` (`9d18312`).

Beads was the tracker for this work and has been removed from the project. This file is now the record. The ids below are the old beads ids, kept only as labels so items can be matched against git history. The last exported snapshot of that tracker is `.beads/issues.jsonl` as of commit `5b25cfb`.

## Blocked on a real Docker daemon

The dev container this repo is worked on from has no docker binary and no daemon socket, so these need a run on the Colima host with the output brought back. As of 2026-08-14, run on the Colima host:

- ~~**Verify the vendored image builds at all**~~ Done. A clean-cache build with no config dir present succeeds, and changing `PADDOCK_TOOLS_REFRESH` rebuilds only the layers below the cache gate (confirmed via `--progress=plain`: layers 1-19 stay `CACHED` on a refresh build, 20-23 rerun for real).
- **Confirm the default CA build context resolves with a real cert.** Still unverified: no machine with a `*.crt` handy to build against `~/.config/paddock/certs/` and check `update-ca-certificates` reports it added. The empty-default half is confirmed (the clean build above never fails for lack of a source).
- ~~**Run the entrypoint verify scripts.**~~ Done. `scripts/verify-entrypoint.sh` now passes all 3 criteria after fixing two script bugs found by running it (not bugs in the image itself): its workdir used plain `mktemp -d`, which resolves outside the host paths Colima shares into its VM, so the `authorized_keys` bind mount came up silently empty — moved under `$HOME`. And its ssh login check compared exact string equality against captured output that also included ssh's "Permanently added to known hosts" notice — added `-o LogLevel=ERROR`. `scripts/verify-entrypoint-local.sh` doesn't need a daemon and already passed.
- ~~**A real end to end pass.**~~ Done. `paddock build`, `up`, `status`, an ssh login, and `down` all worked against a real Colima daemon.

Retiring the agent-container repo (out of tree) is no longer tracked here; Kris is handling that separately.

## Open work needing no Docker

- ~~**Preflight checks**~~ Done. `up`/`start`/`restart` now print a non-fatal warning when `authorized_keys` is missing, since that's the case that silently fails (a container that starts fine and refuses every key) rather than surfacing a `ComposeError`. `docker`/the compose plugin were left alone: a missing `docker` already gets a clean `ComposeError` message, and a missing compose plugin surfaces docker's own stderr directly, so a preflight check there would just add a redundant subprocess call.
- ~~**`paddock init`**~~ Done. Creates the config dir and `certs/` if missing (idempotent), and nudges toward populating `authorized_keys` without creating it itself (an empty file would silently defeat the preflight warning above).

## Small fixes found during integration

- **`glab` install is slightly brittle.** The vendored block uses `grep -o '"tag_name":"[^"]*"' | cut`, which only matches compact JSON with no space after the colon, and it extracts the whole tarball rather than just the `bin/glab` member. Paddock's pre-vendoring copy used `grep -oP` and was more tolerant. This works against today's GitLab API. It was taken deliberately from agent-container, so changing it is a choice, not a bug fix.

## Repo housekeeping

- **No git tags exist.** Consider tagging `9d18312` as `v3.0`.
- **The `milhouse/*` branches are still around.** Their content reached `main` through curated commits rather than merges, so git's `--merged` only recognises three of them. The other five and their worktrees under `~/.herdr/worktrees/paddock/` can be deleted once nobody wants the history.
- **The `.milhouse/runs/` directory is still present.** It holds run logs from the agent runs that produced the 3.0 rewrite. Delete it whenever those are no longer interesting.
