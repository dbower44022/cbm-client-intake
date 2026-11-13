# Kickoff — live check of v0.320.0, an event run by an outside host

Last Updated: 11-13-26 00:20 · Revision 1.1

Operating mode: DETAIL.

Paste this into a fresh Claude Code session in `~/Dropbox/Projects/cbm-client-intake`.

---

Continue `OPEN-ITEMS.md` #80, an event run by an outside host (rulings D3-3 and D3-4, 11-12-26, in `prds/events/CBM_Events_Finalization_Plan.md` row D3). Read #80, `CHANGELOG.md` 0.320.0 and the outside-host entry in `events/CLAUDE.md` first.

State at hand-off: v0.320.0 was pushed 11-12-26; its deployments on crm-test and production started 15:52 UTC (`28117e6f` and `a07b92e5`). The CRM field `CEvent.hostedBy` exists on crm-test only, so production shows nothing new.

Steps, in order. Stop after each and report to Doug.

1. **Confirm the deploy.** Both `/healthz` read 0.320.0, AND the served renderer carries the change: `curl -s https://cbm-client-intake-svxs3.ondigitalocean.app/events-plugin/cbm-events.js | grep -c "Register with the host"` returns 1. A version alone proves nothing.
2. **Live check on crm-test, before 04:00 UTC the same day** (the nightly reset empties `hostedBy` and removes events created that day). As a real non-admin in the Marketing Admin Team: Event Administration → "AI for Small Business" (recreate it if the reset took it: Public, Hybrid, Show this event ticked) → Hosted by → Outside host. The box below must read "Host's link (join or registration page)". Type `partner.example/x` first and save: the save must refuse, naming `https://`. Then type `https://example.com/` and save. Check: the grid reads "Public, outside host"; the Website preview shows the event with **Register with the host**, which opens the link in a new tab; the event's own page (`/webinars/<slug>`) shows the same button and no sign-up form; the Registrants tab shows the outside-host note. Then switch it back to CBM Zoom and confirm the box reads "Join URL" again.
3. **Close the build half of #80** in `OPEN-ITEMS.md`; what stays owed is production and Boston CRM (`cevent-hostedby-crm-handoff.md`, plan fingerprint `6eb4fc2d5940`) at a Sunday slot.

Separately, Doug began connecting Zoom (Track C) on 11-12-26 with the step page https://claude.ai/artifact/Rq3SffAdijgpbWvAijspWB; ask how far he got before starting it again. `EVENTS-SETUP.md` § 5 matches it.

Never `git stash` in this working copy: parallel sessions share it.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.1 | 11-13-26 00:20 | Claude (Claude Code) | Zoom step page noted. |
| 1.0 | 11-12-26 10:54 | Claude (Claude Code) | Created at the close of the 11-12-26 session. |
