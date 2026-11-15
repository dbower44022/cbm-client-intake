# Resume prompt — event hosting, step 4 onwards

Last Updated: 11-15-26 02:20 · Revision 1.0 — see change log at the end.

Paste everything below the line into a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`, **once the Integrations tab's phase 9
(the Zoom Webinars / Zoom Meetings split, `OPEN-ITEMS.md` #82) is committed**.

---

Run `prompts/event-hosting-build-prompt-v0.1.md` from **step 4**. Steps 1
and 3 are done; read before any work:

- `prds/events/event-hosting-plan.md` revision 0.7 or later: § 3 holds what
  the probe proved on a real Zoom Meetings account (personal join links,
  attendance matched by `user_email`, no `registrant_id` in the meeting
  report, capacity 100, the ten scopes); rulings **EH11 to EH14** settle every
  § 6 point (webinar-like meeting settings; Other-platform attendance by hand
  with a no-show warning; a public Other-platform event may be published, its
  shared link only in the confirmation; a hybrid event's method covers its
  online half, the capacity guard warns there). The overlap warning counts
  webinars and meetings under one host user (§ 6 point 5, decided in the
  build session).
- `cevent-hosting-method-crm-handoff.md`: the CRM change, **applied on the
  Business Mentors Association's CRM only** (the test system, `OPEN-ITEMS.md`
  #85). `hostedBy` stores `CBM Zoom` (shown as Zoom Webinars), `Zoom
  Meetings`, `Other platform`, `Outside host`. The Zoom ids on `CEvent` and
  `CEventRegistration` serve both Zoom methods. Not on crm-test, production
  or Boston.
- `scripts/probe_zoom.py --meetings` (the Meetings calls as they were proved)
  and `OPEN-ITEMS.md` #84.

Before step 4: check `git log` for phase 9 and which settings it provides
(Meetings credentials and host, the defaults per audience, the Meetings
capacity limit). If one is missing, stop and tell Doug. The live check
(step 6) runs on the Association: its configuration administrator is
`crm.config` (`~/.config/cbm-bma/bma.env`, `scripts/apply_plan.sh bma …`); a
training-data restore there removes that account until a new baseline is
taken. The Association's Zoom app already holds the ten meeting scopes; its
co-host setting (`in_meeting.co_host`) is still unread.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 11-15-26 02:20 | Claude (Claude Code) | Written at the end of the session that did steps 1 and 3 and settled plan § 6. |
