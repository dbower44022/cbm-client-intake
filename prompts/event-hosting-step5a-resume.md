# Resume prompt — event hosting, readiness before the live check (plan § 8)

Last Updated: 11-21-26 23:58 · Revision 1.0 — see change log at the end.

Paste everything below the line into a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`.

---

**Operating mode: DETAIL** (this repository's default). The first reply
states the operating mode and the `CLAUDE.md` files loaded. Open every reply
with the local time read from `date`; never guess it.

**One Events session at a time.** Ask Doug whether any other session is
working in `events/` before starting.

## Where it stands

Read first, in full: `prds/events/event-hosting-plan.md` (rulings EH1 to
EH14; § 8 with rulings R1 and R2), `events/CLAUDE.md` (the Hosting methods
section) and `OPEN-ITEMS.md` #84.

- Steps 1 to 5 of the plan are built and live (v0.341.0 to v0.342.2).
- The step 6 live check on the Business Mentors Association's system
  (11-17/18-26) stopped at section 8. Four failures were found one at a time
  by Doug following a 100-step page, none of them in the hosting build:
  - the worker ran with Events off;
  - the eight email templates were missing;
  - no worker confirmation had ever rendered;
  - attendees could share their screens.

  Doug: "Let's stop this and build a better process with better tools."
- Plan § 8, items 1 to 3, are built and live (v0.344.0 and v0.347.0). The
  worker reports its switches. The Event hosting card on System Settings →
  Feature readiness reads them all live. Its fix buttons are confirmed with a
  second click.
- On 11-18-26 the card read ready on every line except **Screen sharing — all
  participants** for the event host user `admin@mentorsassociation.org`.

## What to do

1. **The Zoom fix button, first.** Doug has never clicked it. Ask him to
   reload Feature readiness and click **Set host-only sharing and co-host**
   twice. If Zoom refuses for lack of the permission
   `user:update:settings:admin`, write the steps to add it on the Zoom App
   Marketplace (the app's Scopes page, **Add Scopes**). The scope's name comes
   from a mirror of Zoom's reference, not Zoom's own page: confirm it there
   first. If Zoom accepts the change but the read-back still shows
   all participants, the account may lock the setting. Say so, and stop.
2. **Item 4**: a test that runs a delivery through the real
   `core/resumable.ResumableClient` end to end, confirmation included. The
   missing `email_template_prepare` pass-through hid there for weeks behind
   fakes.
3. **Item 7b of #84**: `confirm.skip_reason` should name which condition
   failed, not "not switched on".
4. **Item 5**: the shorter live check. **Before writing a single step**, run
   every read-only check yourself:
   - the Event hosting card's checks (`events/readiness.py`, which can be run
     against the Association's CRM through `scripts/run_with_admin.py --env
     ~/.config/cbm-bma/bma.env`);
   - the worker's log (`doctl apps logs 1944c6a4-ac65-4982-bad1-d3f637d91fb5
     delivery-worker --context bma`);
   - `/healthz`.

   The page holds only what needs a person: about 15 steps. It cleans up what
   the 11-17/18-26 run left (#84) and reuses nothing from the old page
   (https://claude.ai/artifact/Fh8pdPmKZHvBsZUazqCPfy, kept as the record).
5. Then production and the chapters, on a separate page at a Sunday slot.

## Rules this session follows

- Another session works in the same checkout. Commit with an explicit path
  list. Never sweep another session's uncommitted lines in the shared files
  (`CHANGELOG.md`, `CLAUDE.md`, `OPEN-ITEMS.md`, `pyproject.toml`,
  `uv.lock`): if one has them open, commit the code first and the version
  after it commits. Read `git log` for the current version and
  `uv run alembic heads` before choosing one.
- Run the full suite in a scratch worktree holding only this session's files.
- Commit; Doug reviews and pushes.
- Every instruction to Doug follows the Step-by-Step Instructions standard,
  verified against the live system first. Never ask Doug to read something
  you can read yourself.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 11-21-26 23:58 | Claude (Claude Code) | Written at the close of the session that built steps 4, 5 and § 8 items 1–3. |
