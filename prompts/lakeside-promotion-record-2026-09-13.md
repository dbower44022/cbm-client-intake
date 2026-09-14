# Record the 2026-09-13 Lakeside promotion, and make the promote script wait for the container

Last Updated: 09-14-26 00:50 · Revision 1.1 — see change log at the end.

> **DONE — both parts shipped, under different version numbers. Do not execute
> this document.** It is kept as the record of what was asked, the way every
> other file in `prompts/` is. The session it was written for carried it out on
> 2026-09-13 while the version had already moved past 0.226.1, so:
>
> - **Part 1** landed in `54613c8`, *docs(chapters): record the 2026-09-13
>   promotion and the one-operation update* — all three chapter documents now
>   record the second promotion.
> - **Part 2** landed in `03aa981`, *feat(chapters): upgrading a chapter is one
>   operation (v0.228.0)* — `scripts/promote.py` waits up to two minutes for
>   `/healthz` to report the new tag before judging. There is **no v0.226.1**;
>   the fix arrived inside a larger change that also moved the tag into
>   `release-tag.txt` at cut time.
>
> Following the steps below as written would bump the version *backwards* and
> re-add text that is already there.

Written in the CRMBuilder session on 09-13-26 for a session rooted in this
repository. Two pieces of work, both small. Follow this repository's `CLAUDE.md`
conventions: Conventional Commits, Claude commits and Doug pushes, a code change
bumps the version and gets a changelog entry.

## What happened

On 2026-09-13 (00:51 UTC on 09-14) Doug promoted `lakeside-intake` to v0.226.0:

- The tag `v0.226.0` was cut by hand at `origin/main` commit `e6c103e`
  (`git tag -a v0.226.0 origin/main …`), because `scripts/cut_release.sh`
  refuses a dirty working tree and another session held uncommitted work.
- `release` was fast-forwarded to that commit (`git branch -f release`) and
  both were pushed: `git push origin v0.226.0 release`.
- `uv run python scripts/promote.py 362feb29-5dcd-47cb-97d5-b44530ebc2dc v0.226.0 --apply`
  set `RELEASE_TAG=v0.226.0` on `web`, `delivery-worker` and `migrate`, and the
  deployment went ACTIVE.
- The script's final health read ran a few seconds before the new container
  answered on the public address, so it printed
  `reported releaseTag: 'v0.217.0' -> None (version None, crmConfig None)` and
  `the promotion did NOT land as asked` — a false failure. Five minutes later
  `/healthz` reported `version 0.226.0`, `releaseTag v0.226.0`,
  `crmConfig unstamped`, worker heartbeat under two seconds. Verified three
  times from the CRMBuilder session.
- Versions v0.218.0 through v0.225.1 were never tagged. The Sunday slots of
  09-06 and 09-13 (17:00 UTC) passed without a cut; this cut ran late on 09-13.
- Cleveland production and crm-test still carry `RELEASE_TAG=v0.217.0` in
  their overlays while running 0.226.0; Doug is refreshing those separately.

## Part 1 — the record (docs only)

Make these edits. Keep every other sentence as it is.

1. `prds/chapter-network/README.md`, the *Where it stands* table, row
   **2 — Release train**, last column. Replace
   `R10 is done — the first promotion ran for real (\`lakeside-intake\` → v0.217.0). Next: cut on cadence each Sunday; Cleveland's \`deploy_on_push\` stays on until the train is trusted`
   with
   `R10 is done, and the lane has carried two promotions (\`lakeside-intake\` → v0.217.0 on 2026-08-31, → v0.226.0 on 2026-09-13). The 09-06 slot was missed and the 09-13 cut ran late; v0.218–v0.225 were never tagged. Next: cut on cadence each Sunday; Cleveland's \`deploy_on_push\` stays on until the train is trusted`.

2. `prds/chapter-network/phase-2-release-train.md`, the opening **Status**
   paragraph. After the sentence ending `…and verified at \`/healthz\`.` add:
   `The second promotion ran on 2026-09-13: v0.226.0, tagged by hand at \`origin/main\` because the cut script refuses a dirty tree, then \`promote.py --apply\`. The script's final health read raced the new container and reported a false failure (fixed in v0.226.1 — it now waits for the container to answer).`
   In the *What remains of this phase* sentence, leave the text as it is.

3. `prds/chapter-network/TASKS.md`, § R10, the opening bold paragraph. After
   the sentence ending `…all three components on the \`release\` branch).` add:
   `Second promotion 2026-09-13: \`lakeside-intake\` → v0.226.0, the same two operations. Found live: the post-ACTIVE health read races the new container (DigitalOcean reports ACTIVE seconds before the public address serves the new revision), so the script declared a false failure; fixed in v0.226.1 by waiting up to two minutes for \`/healthz\` to report the tag.`

4. Update the memory note for the Lakeside instance if this session keeps one
   (the CRMBuilder session already updated
   `~/.claude/projects/-home-doug-Dropbox-Projects-cbm-client-intake/memory/lakeside-rehearsal-instance.md`).

Commit Part 1 on its own as a `docs(chapters):` commit with an explicit
pathspec naming the three files. Do not commit anything else that is sitting in
the working tree.

## Part 2 — the promote script waits for the container

In `scripts/promote.py`, function `main`, after the wait loop ends and before
the line `print(f"deployment phase: {phase}")`, the current code reads:

```python
    after = healthz(url) if url else {}
```

Replace it with:

```python
    # DigitalOcean reports ACTIVE a few seconds before the public address serves
    # the new revision. One read there sees the old container, or nothing, and
    # the script then declares a false failure (seen 2026-09-13). Wait for the
    # tag to appear, up to two minutes, before judging.
    after = healthz(url) if url else {}
    settle_deadline = time.time() + 120
    while url and after.get("releaseTag") != args.tag and time.time() < settle_deadline:
        time.sleep(10)
        after = healthz(url)
```

Also add to the module docstring, under the "2." paragraph, one sentence:
`After ACTIVE the script waits up to two minutes for /healthz to report the new tag, because the platform reports ACTIVE before the public address serves the new revision.`

Then:

- Bump `pyproject.toml` to `0.226.1`.
- Add a `## [0.226.1]` changelog entry: `fix(chapters): the promote script waits for the new container before judging the promotion` — say what happened on 2026-09-13 and that the promotion had in fact landed.
- Run `uv run pytest -q` and report the result.
- Commit Part 2 on its own as `fix(chapters): … (v0.226.1)` with an explicit
  pathspec: `scripts/promote.py pyproject.toml CHANGELOG.md`.
- Do not push. Print the two commit hashes and stop.

## Change log

| Rev | Date | Author | Change |
|---|---|---|---|
| 1.1 | 09-14-26 00:50 | Claude (Claude Code) | Marked done. Both parts were carried out on 2026-09-13 — Part 1 in `54613c8`, Part 2 inside `03aa981` (v0.228.0) rather than the v0.226.1 asked for, because the version had moved on. Header added so the document is not executed a second time. |
| 1.0 | 09-13-26 21:05 | Claude (CRMBuilder session) | First draft. |
