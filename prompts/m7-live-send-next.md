# Kickoff — after M7: the live send, then M8

Last Updated: 10-26-26 12:16 · Revision 1.0 — change log at the end.

Operating mode: DETAIL. The first reply states the mode and the loaded
`CLAUDE.md` files as usual, reads `git log origin/main..main` and says what
is unpushed, then asks Doug which of the two jobs below to start.

## Where things stand (10-26-26 12:16)

- **v0.290.0 (M7) is built and committed, not pushed**: `3284a28`, plus the
  docs commit `1cf93fd`. A list keeps a copy in Constant Contact; an email
  campaign must choose a list, writes no touch at build, syncs the copy at
  sign-off, and picks the email Doug sent (rulings 95, 126; Doug's rulings
  1-a and 2-b at the M7 plan). Dark behind `CAMPAIGN_LIST_SYNC`; migration
  0038. Record: `CHANGELOG.md` 0.290.0, build plan § 7e.13 step 7,
  `OPEN-ITEMS.md` #57, `campaigns/CLAUDE.md` rev 1.14.
- **The live send is owed.** Step page
  https://claude.ai/artifact/3YmoAaiHHAi2XFcJYAfK47 (37 steps; step 2 is
  the push). Run it in one day, before 04:00 UTC. Doug may ask Claude to run
  it in a tab he signs in as Mark Marketing.
- **Not confirmed until the send:** the custom-field endpoints, the
  `cf:cbm_lead_code` import column, the `[[custom.cbm_lead_code]]` merge tag,
  the list rename, and the email-campaign listing (`core/mailing.py`'s
  integration notes mark each inferred).

## Job 1 — the live send's outcome

When Doug sends back the checkpoints (or Claude runs the pass):

1. Record each vendor shape's outcome under build plan § 7e.12 Draft 8 (the
   *M7's inferred shapes* bullet): confirmed, or corrected with the vendor's
   real shape.
2. Fix any shape that was wrong as a patch release (0.290.x), with a test
   that pins the real shape; mark it *read* in `core/mailing.py`.
3. Update `OPEN-ITEMS.md` #57, the root `CLAUDE.md` status block for
   v0.290.0, and the build plan's M7 entry (live-passed, with the time).

## Job 2 — M8: lists only and the campaign page

Build plan § 7e.9 second half (rulings 99–102): the ready-made system lists
(a migration after 0038), the rule cards gone for every kind, the progress
strip, the six tabs, the grid, + New campaign. Write its kickoff plan as a
draft for Doug's approval first, in the shape of
`prompts/m7-constant-contact-kickoff.md`. The handoff's § 7 layout question
is still open.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-26-26 12:16 | Claude (Claude Code) | Written at the close of the M7 build session, before a reboot. |
