# Kickoff prompt — the home page, phase 5: Chapter News core

Last Updated: 11-20-26 01:30 · Revision 0.1 — see change log at the end.

**Draft for Doug's approval.** Written 11-20-26 at the close of phase 4
(v0.351.0, At the chapter; stop 4 passed the same day). Start a fresh
Claude Code session rooted in `~/Dropbox/Projects/cbm-client-intake`, tell
it to read this file, and tell it to follow everything below the line.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
three stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

**Another session may be working in this checkout at the same time.** It
happened on every phase so far. Before choosing a version number, read
`git log`, the working tree's `pyproject.toml` and the top of
`CHANGELOG.md`, and take the next free one; never take numbers from this
prompt. **Before staging, run `git status --short`.** A file another
session has edited and not committed (`CHANGELOG.md`, `CLAUDE.md` and
`OPEN-ITEMS.md` most often) is never staged whole: stage only your own
lines (write the index copy from `git show HEAD:<file>` plus your change
with `git hash-object -w` and `git update-index --cacheinfo`), commit, and
audit with `git show --stat` and `git show --word-diff` on those files.
The two sessions share one index, so check right before committing that
your staged lines are still staged.

Read, in full, before any code:

- `prds/home-page-plan.md`: the plan. **Rulings 1 to 9 are settled; do not
  re-open them.** This phase builds § 8's phase 5, to § 6 (Chapter News:
  what the member sees, what the publisher sees, the rules, the data), in
  the look of § 5. Rulings 4, 5 and 6 decide where news is written and
  stored: on a Chapter News page in this application, every record in the
  CRM, read receipts as CRM records. **Read reports are phase 6 and the
  weekly digest phase 7: out of scope here.**
- `prompts/home-page-mix-mockup.html`: the Chapter News panel as sample
  data (lines 40 to 70: "3 unread", an item to acknowledge, a call to
  action).
- The `espo-crm-changes` skill, **before writing any CRM step**, and
  `prds/chapter-network/crm-update-runbook.md` (its § 7 is the twelve
  traps). The root `CLAUDE.md` "EspoCRM behaviour" gotchas apply in full:
  the entity name always gains a `C` (type `ChapterNews`, get
  `CChapterNews`; type `CChapterNews`, get `CCChapterNews`), the Create
  Link dialog inverts its two Name boxes, a Read-only field drops every API
  write, a list `maxSize` over 200 is a 403, a system entity may not be
  customizable (check `scopes.Team.customizable` before planning
  `audienceTeams`), and a role creating records needs Assignment Permission.
- `scripts/migrate_event_schema.py` and `scripts/migrate_grant_schema.py`:
  the worked examples of building entities and links through the API,
  dry run by default, reading every link back.
- The root `CLAUDE.md`: "Portal + authentication" (the new home page lines
  and endpoints), "Events & Webinars" (`events/visibility.py` as the model
  of one visibility rule that every surface calls), "Conventions"
  (busy.js, textsize.js and no bare `vh`/`vw`, buttons never disabled or
  hidden, the shared grid, CBMRichText and its `uploadImage` hook, the
  `{{org}}` and `{{abbr}}` tokens, `core/action_log.py` for every
  publisher action, feature-detecting a CRM field from metadata), and the
  "A 403 and a 404" gotcha.
- Phases 1 to 4's code, which this phase extends: `portal/router.py`
  (`_home_sections`, the `/home/*` reads, `_shared`, `PREFERENCE_KEYS`),
  `portal/needs.py`, `portal/chapter.py`, `portal/frontend/home.js`,
  `home.css`, `frontend/shared/panel.css`.
- `frontend/shared/richtext.js`, `core/inline_images.py` and one host that
  passes `uploadImage` (the session notes editor): how an inline image
  becomes an attachment on a live wysiwyg field.
- `setup/CLAUDE.md` and `core/settings_registry.py`: a new setting
  (`NEWS_PUBLISH_ALLOWED_TEAMS`, the `CHAPTER_NEWS` switch) gains its row in
  `tests/fixtures/setup_payload_before_integrations.json`.
- `OPEN-ITEMS.md` #87 (the Association's owed baseline re-capture) and #89.

## Scope of this phase

Plan § 8's phase 5, behind a new switch `CHAPTER_NEWS`, off by default, and
behind `HOME_V2` for the home page's part:

1. **The CRM build**: `CChapterNews` and `CChapterNewsReceipt` (§ 6.4), one
   handoff `cchapternews-entities-crm-handoff.md` in Entity Manager
   vocabulary, and an idempotent build script in the pattern of
   `migrate_event_schema.py`. **Applied on the Association's CRM first,
   and only there in this phase.** The feature detects both entities from
   metadata and stays dark until they exist.
2. **The Chapter News section** on the home page (§ 6.1): unread items,
   those to acknowledge first, then pinned, then the rest, newest first;
   title and summary, opening to the full body; the call-to-action button;
   **Dismiss**, or **I have read this** for an item to acknowledge (the
   section cannot be hidden while one is unread, § 4.3); with nothing
   unread it shrinks to a **Past news** link.
3. **Past news**: every item the member could see, newest first, dismissed,
   acknowledged and expired ones included.
4. **The Chapter News page** for publishers (§ 6.2): the list with status
   and publish date, the editor (`CBMRichText` with `uploadImage`), a live
   preview of the item as a member sees it, audience, importance, publish
   date, expiry date, call to action, and **Withdraw**. Its tile shows only
   to publishers. Every publisher action recorded through
   `core/action_log.py`.
5. **The rules** (§ 6.3) in one module every surface calls, as
   `events/visibility.py` is for events: who may see an item (audience,
   status, publish and expiry dates), never re-filtered elsewhere.
6. **Each part fails on its own**, wrapped in `CBMBusy.loading`.
7. **Tests**: the visibility rule (audience, every status, the two dates,
   a member who joins later), the order, dismiss and acknowledge (a second
   click finds the existing receipt), the section that cannot be hidden,
   withdraw, the publisher gate, the switch off, the CRM feature detection,
   the settings and their fixture rows, the branding guard.
8. **Records**: version bump and `CHANGELOG.md`; `OPEN-ITEMS.md` #89 and a
   line on which CRMs hold the two entities; the plan's status line, § 6
   and § 8; the root `CLAUDE.md` home page lines; a staff guide for
   publishers.

Out of scope: read reports (phase 6), the weekly digest and its opt-out
(phase 7), posting news to the public website (ruling 4), comments and
reactions (§ 7), and the CRM build on crm-test, Cleveland's production or
any chapter's CRM.

## Stopping point (a) — before building

Put to Doug, each as one question with options, their costs, and a
recommendation, then stop. **Verify each premise against the code, the
skill and the Association's CRM first** (read-only), and name what you
verified.

- **One phase or two.** Phase 5 is the largest so far: a CRM build, the
  member's section, past news and the publisher's page. Build it as one
  release, or as 5a (the CRM build, the member's section and past news,
  with items made by a script for the check) and 5b (the publisher's
  page). Name the cost of each in checks Doug runs and in how long a
  feature sits half-built.
- **Audience by team**: whether a custom entity can hold a many-to-many
  link to `Team` on the Association's CRM (read `scopes.Team` and the
  link rules), and if not, what stands in for it (a multi-select of team
  names, kept in step with the CRM's teams), with its cost.
- **Who reads and writes in the CRM**: members read news and write
  receipts under the org-wide key (§ 6.4, so members need no new
  permissions), publishers write items as themselves or under the key.
  Name the role grants each choice needs on the Association, and whether
  a publisher's own role can be left alone.
- **Who publishes**: `NEWS_PUBLISH_ALLOWED_TEAMS`, default System
  Management Team (§ 6.3). Verify that team exists on the Association and
  who is in it; name who could publish on the test system on day one.
- **Where publishing lives**: a new application tile ("Chapter News") with
  its own route, or a tab of an existing staff application. § 6.2 says a
  page with its own tile; confirm before building.
- **Images in a news body**: inline attachments on `CChapterNews.body`
  through `core/inline_images.py` and an application proxy. Members must
  be able to see them; name how a member's browser reaches them (the same
  proxy, read under the key) and what that costs.
- **Expired items to acknowledge** (§ 6.3: an expired item stops
  prompting): confirm, and whether an unacknowledged expired item shows in
  past news as unacknowledged.
- **The read and its cost**: one `GET /api/portal/home/news` for the
  section and one for past news; CRM calls per sign-in (the `timing` log
  line on the Association is the measure); whether the items, being the
  same for everyone in an audience, are kept for the whole application and
  for how long, given that a publish or withdraw must show promptly.

Show the answers on one rendered screenshot of the News section and the
Chapter News page with sample data if that settles them faster than
words.

## Stopping point (b) — the CRM build, before any application code

Write the handoff and the build script, run the script's dry run against
the Association's CRM, and show Doug the plan it prints. **The apply is
Doug's to run** (writes to a CRM are run by him with `!`, or on his
explicit go-ahead), then verify the build in `GET /Metadata` as the
org-wide key **and** as a real non-administrator (`joe.mentor@bma.test`),
and stop. The application code starts only after the build is verified.

## Stopping point (c) — after building

Commit. Then write Doug the check as a runbook page, following his
step-by-step instructions standard: push; switch `CHAPTER_NEWS` and
`HOME_V2` on at the Association's System Settings; as a publisher, publish
one item of each importance (normal, pinned, must acknowledge), one with an
image and one with a call to action, one limited to an audience team; sign
in as Joe Mentor, Kitty Cat and Mark Marketing and see exactly the items
each should see, in the right order; dismiss one, acknowledge one, and see
the section refuse to hide while an item waits; open past news; withdraw
an item and see it vanish for everyone, past news included; switch both
off. Raise the Association's owed baseline re-capture (#87) first: every
item and receipt made for the check stays in its CRM. Close the phase only
after Doug's check (plan § 8, stop 5).

## Change log

| Revision | Last Updated | Change |
|---|---|---|
| 0.1 | 11-20-26 01:30 | First draft, written at the close of phase 4. |
