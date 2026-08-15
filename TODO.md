# TODO

Open work. Completed items are dropped from this file once their rationale lives somewhere durable (`AGENTS.md` for design decisions, git history for the rest) rather than being kept here struck through.

Beads was the tracker for this work and has been removed. The last exported snapshot is `.beads/issues.jsonl` as of commit `5b25cfb`, and old beads ids (`paddock-96h`, `paddock-aye`, `paddock-3t0`) still appear in git history as labels.

## Needs a real Docker daemon

- **Confirm the CA build context resolves with a real cert.** The only image behavior still unverified. Needs a `*.crt` in `~/.config/paddock/certs/` and a build that shows `update-ca-certificates` reporting it added. The empty-default half is confirmed: a clean build with no config dir present never fails for lack of a source. Everything else about the image (clean build, cache gate split, entrypoint, runtime user, signal handling, end-to-end ssh) passes.

## Deliberate non-fixes

- **`glab` install is slightly brittle.** The vendored block uses `grep -o '"tag_name":"[^"]*"' | cut`, which only matches compact JSON with no space after the colon, and it extracts the whole tarball rather than just the `bin/glab` member. paddock's pre-vendoring copy used `grep -oP` and was more tolerant. This works against today's GitLab API, and it was taken deliberately from agent-container, so changing it is a choice rather than a bug fix.

## Repo housekeeping

- **Nothing is pushed.** `main` is ahead of `origin/main`, and neither the `v3.0` tag (on `9d18312`) nor the `v4.0` tag (on `196e7b4`) exists on the remote. The sandbox this work was done from has no outbound network, so these need `git push origin main` and `git push origin v3.0 v4.0` from a shell that does.
- **The `milhouse/*` branches and `.milhouse/runs/`** aren't present in this checkout — already cleaned up, or they only exist on another machine. Nothing to do unless they turn up.
