# Resume prompt — event Overview tab + the crm-test upload repair

Last Updated: 09-17-26 11:44 · Revision 1.0 — see change log at the end.

Paste this into a fresh Claude Code session rooted in `cbm-client-intake`.
It carries the state of the work interrupted by a reboot on 09-17-26.

---

## Kickoff

Operating mode: ARCHITECTURE.

Read `CLAUDE.md` in this repository first and confirm it is the one in force.

Two pieces of work are finished in the local clone and **not pushed**. Nothing
is half-written; the code is complete and the suite is green. What remains is a
push, six commands on the crm-test droplet that only Doug can run, and a live
look in a browser.

### Where the work stands

Three commits sit on `main` ahead of `origin/main`:

| Commit | What it is |
|---|---|
| `3215f5c` | **v0.231.0** — the event Overview tab shows the whole record |
| `2c2dd1f` | **v0.231.1** — the sandbox upload repair, and the editor shows its messages |
| `900f341` | lockfile version bump + the Overview tab's owed live pass in `OPEN-ITEMS.md` |

`git log origin/main..main --oneline` is the truth; this table is a
convenience. **Doug pushes, not Claude** — that is the repository's standing
convention.

Full suite at the point of interruption: 2,055 passed, 25 skipped.

### What v0.231.0 changed

The Overview tab of an event in `/events` is now the whole record, read-only,
so staff can check an event without opening the editor. Facts on the left,
driven by the same `EVENT_FIELDS` spec the editor is built from, so a field
added to the spec appears on the view screen with no second edit. The event
graphic, Summary, Full description and Syllabus on the right, the last two
rendered as HTML through the shared `CBMRichText` sanitizer. Every slot renders
even when empty. `PUBLIC_SELECT` gained `registrationUrl`, which the field spec
declared and the Zoom sync wrote but no read had ever selected.

Verified in a fetch-stubbed browser harness only. The live pass is
`OPEN-ITEMS.md` #20, first sub-bullet.

### What v0.231.1 changed, and why it matters beyond events

Doug reported that uploading an event graphic did nothing. The cause was not in
the application. The crm-test droplet's nightly sandbox reset restores
`data/upload` and `chown`s it to `1000:1000` — the host user — while the
EspoCRM container runs as `www-data` (uid 33). Reads survived, writes did not:
since the reset went live on 08-22-26, **every** `POST /Attachment` on crm-test
has failed with *Permission denied for data/upload/&lt;id&gt;*. Event graphics,
mentor photos, inline wysiwyg images and document uploads were all affected on
that environment. Production has no reset and was never affected.

`scripts/sandbox/reset_crm_sandbox.py` now takes the owner from the parent data
directory (`upload_owner`) rather than a hard-coded id. Separately, the event
editor's `notice()` writes into the modal's own message slot while the modal is
open, because the page banner sits *behind* the overlay — which is why a CRM
500 read as "nothing happened".

Memory: `sandbox-reset-upload-ownership`. Runbook note: `SANDBOX-RESET.md`,
after the baseline-capture step.

## The next required step

**`OPEN-ITEMS.md` #32** holds the whole list. In order:

1. Doug pushes `main`. This builds dev, crm-test and production.
2. Doug copies `scripts/sandbox/reset_crm_sandbox.py` to
   `/usr/local/sbin/reset_crm_sandbox.py` on `root@104.131.45.208`.
3. Doug runs `chown -R 33:33` once on
   `/var/www/espocrm/data/espocrm/data/upload`.
4. Doug confirms crm-test reports `0.231.1` at `/healthz`, then uploads a
   graphic through `/events` and sees **Graphic saved.** in the editor.
5. The same visit covers the Overview tab's live pass (`OPEN-ITEMS.md` #20).

The step-by-step runbook, with copy buttons and the expected output of each
command, is published at
<https://claude.ai/artifact/Ar7zjXmCfDqR2tMhfzrtPF>. Re-issue those steps in
full in chat if Doug asks for them again; do not condense them.

**Claude cannot run steps 2 and 3** — the tool classifier blocks mutating SSH.
Doug runs those himself, or with a `!` prefix in the session.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 09-17-26 11:44 | Claude (Claude Code) | Written at the end of the 09-16/09-17 session, interrupted by a system reboot. Carries the three unpushed commits, the cause of the crm-test upload failure, and the ordered list of what is owed. |
