# Kickoff prompt — define the Campaign Management application

> **Done — history.** This kickoff was run and its product is recorded; it was
> moved here on 10-14-26 when the arc was consolidated into
> `prds/prospect-marketing/`. Paths below predate the move; start at the
> directory's `README.md`.

**Written 10-14-26 17:20. For a fresh Claude Code session rooted in
`cbm-client-intake`.** This is a **definition session**: its product is a
requirements record for the application marketing users will use to create
campaigns and the links that carry a campaign into the intake forms. It is
not a build session and not a plan session. Nothing is built, no CRM is
changed, no vendor account is opened.

Operating mode: DETAIL. "Define" means **elicit Doug's requirements first**;
anything the assistant drafts is a strawman, labelled as one, and never
recorded as decided.

---

## The prompt

On 10-14-26 Doug ruled (`prds/prospect-marketing-plan.md`, rulings 26 and
27) that **Campaign is a new entity created by marketing users; each campaign
owns one or more links; a link opens one of the standard intake forms
carrying the campaign's id; the records the form creates carry that id** —
on the relationship record every time, on the Contact and Company only when
that submission created them. The postcard is a campaign whose link rides in
its QR code. Source stays what the person says on the form.

Your job is to find out, from Doug, one question at a time, **what the
Campaign Management application is**: who uses it, what a campaign is to
them, what a link is, what the application shows them afterwards, and where
it lives among the existing tools. Record what comes out as a requirements
section of the plan. You decide nothing on your own.

### Read first

1. This repo's `CLAUDE.md` in full — especially *The applications* (every
   staff tool has the same shape: a package with `service.py`, `router.py`,
   `frontend/`; one declared field spec serves as both layout and write
   whitelist; team gates; action logging), the Events section (Event
   Administration is the closest existing marketing tool, and the Marketing
   Admin Team already gates Submission Admin), and the Conventions.
2. `prds/prospect-marketing-plan.md` — the 2026-08-11 rulings 1–8 and the
   2026-10-13/14 section, rulings 9–27, in full. **All are settled; do not
   reopen them.** Note in particular: Active Prospect is membership in a
   running campaign (ruling 10); the three campaign kinds that came out of
   the walk — postcard, email, call — and each one's selection rule (rulings
   10, 19, 20); the approval gate (13); one card per company (14); the
   dormant-client campaign as a selection rule (25); the campaign is the
   reportable label the touches are stamped with (the withdrawn "reach"
   proposal explains why).
3. **The partner intake link, the working precedent for a campaign link**
   (v0.255.0): `sessions/router.py` around line 539 and
   `sessions/service.intake_referral_link` build the link from
   `APP_BASE_URL`; `forms/client_intake/frontend/index.html` and `app.js`
   carry the id in a hidden field and show a banner from a public name-only
   lookup that 404s on anything it cannot resolve; `forms/client_intake/
   schemas.py` and `orchestrator.py` capture it in the payload and write it
   at delivery after a validate-or-drop read. Read all of it before asking
   anything about links, so every question is grounded in what exists.
4. `prds/mailing-list-and-event-sponsorship-plan.md` §§ on Constant Contact
   — Constant Contact has its own "campaigns" (email sends). The word is
   going to collide. Verify what Constant Contact calls them and what the
   app's mailing settings page already says, before the naming question.
5. `prompts/prospect-marketing-build-plan-prompt-v0.1.md` — the build plan
   session that follows; this session's record is one of its inputs.

### What is settled, what is not

**Settled:** rulings 1–27. The campaign entity exists; marketing users create
it; a campaign owns one or more links; a link opens a standard form with the
campaign id; which records carry the id; what Source means.

**Open, and the point of this session** — put each to Doug, one per turn,
in roughly this order, skipping any he answers on the way:

1. **Who uses it.** The Marketing Admin Team (Submission Admin's gate, Event
   Administration's role) or a new team; whether a mentor or partner
   manager ever creates a campaign.
2. **What a campaign is to its user.** A named thing with a kind (postcard,
   email, call, dormant-client, webinar promotion…), a date range, a status
   (draft / approved / running / closed), an owner, a budget — or less. What
   fields he actually wants to fill in, and what he never wants to see.
3. **What a link is.** One per form per campaign, or any number; whether a
   link carries more than the campaign id (a prospect id for the postcard
   case, a partner id — the two links already coexist on the client intake
   form); whether a link can point at the webinar page or an event's own
   page as well as the five intake forms; whether a link has its own name
   and its own count.
4. **What the links look like.** A short opaque token versus the CRM id
   (ruling on the partner link: the CRM id); whether a link can be turned
   off; whether the QR code is generated here or by the mail vendor.
5. **What the application shows after the campaign runs.** Per link and per
   campaign: opens (the banner lookup already counts as an "open"),
   submissions by form, the records created, conversion to Candidate and
   Client read from the engagement. Which of these are Analytics panels
   (`ANALYTICS_ENABLED`, metric library) and which belong on the campaign's
   own screen.
6. **Where it lives.** Its own portal tile, a tab inside Event
   Administration, or a section of Submission Admin. A record page per
   campaign, the stable-tab convention.
7. **Naming**, last, once everything else is known: whether the UI word is
   *Campaign* given Constant Contact's use of it.

### How to run the session

Doug wants a **conversation**, not a document review. The rules, learned the
hard way (`doug-wants-conversation-not-option-menus`):

- **One question per turn**, in prose, with your recommendation and the
  reason before it, and its cost named. No option menus, no bulleted lists
  of issues, no `AskUserQuestion`.
- **Executive register.** Short paragraphs, plain words. Say what the user
  sees and does; leave entity and field names out unless he asks.
- **Verify a premise before asking about it.** If a question depends on how
  the app or CRM behaves today, read the code first.
- **Record what he says as his; record what you think as yours.** Nothing
  becomes a requirement unless he states it. A strawman screen sketch is
  allowed when it makes a question concrete, labelled as a strawman.
- **Answering a question does not advance.** If he asks what a term means,
  answer inside the current question and stop.

### Guardrails

- **No code, no CRM changes, no vendor accounts.**
- **Do not reopen rulings 1–27.** If a requirement he states cannot be met
  under one of them, say which ruling and why, in a sentence, and ask.
- **Chapter-network vocabulary.** Nothing Cleveland-specific in a name a
  second chapter would have to change.
- **The link must stay honest about privacy.** A campaign link shows the
  visitor nothing the chapter knows about a person (the 2026-08-17 harvester
  ruling); the postcard landing page shows only what is printed on the card
  (ruling 16). A link that prefilled a form from a record would break both.
- **No page width caps; every button always clickable** (`CLAUDE.md`
  Conventions) — note them in the record where a requirement touches a
  screen, do not re-litigate them.

### At the end of the session

Add a dated section **Requirements — Campaign Management application
(MM-DD-YY)** to `prds/prospect-marketing-plan.md`, in three labelled kinds:
Doug's requirements (stated, dated), working positions (said in discussion,
may be revised) and strawmen (yours, not adopted). Include a compact table of
the campaign's fields as Doug named them, the link's shape, the screens, and
what is still open. Bump the draft version, update the revision table and the
change log (Last Updated in MM-DD-YY HH:MM, read from the clock). **Commit;
do not push** — Doug reviews and pushes. Then state the next step: normally
the build-plan session (`prompts/prospect-marketing-build-plan-prompt-v0.1.md`),
which should now read this section too — add it to that prompt's *Read
first* list in the same commit.

---

## Revision control

| Field | Value |
|---|---|
| Document | Kickoff prompt — define the Campaign Management application |
| Version | v0.1 |
| Last Updated | 10-14-26 17:20 |
| Prepared by | Claude (Claude Code), for D. Bower |
| Related | `prds/prospect-marketing-plan.md` (rulings 26–27), `prompts/prospect-marketing-build-plan-prompt-v0.1.md` |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| v0.1 | 10-14-26 17:20 | Claude (Claude Code) | Written at Doug's request at the close of the 2026-10-13/14 discussion session, after rulings 26 and 27 created the Campaign entity and its links. |
