# Kickoff prompt — the home page, phases 5 to 7 and the fixed header, in one session

Last Updated: 11-20-26 01:40 · Revision 0.1 — see change log at the end.

**Draft for Doug's approval.** Written 11-20-26 at the close of phase 4, at
Doug's request: "write a prompt to complete 5, 6 and 7 in one new session
without user prompts. Include the fixed header bar. Then we will do one
big test." It replaces `prompts/home-page-phase5-prompt-v0.1.md`, which is
kept for its reading list. Start a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`, tell it to read this file, and tell
it to follow everything below the line.

---

## Kickoff

**Operating mode: DETAIL, with one stopping point, at the very end** (Doug,
11-20-26: one session, no user prompts, one big test). Under the global
rule, a DETAIL plan names its stopping points and work between them
proceeds without asking; this prompt is that plan and names only one. **Do
not stop to ask Doug anything before the end.** Where a question would
normally stop the work, take the default this prompt gives (§ Decisions
taken in advance), or, where it gives none, choose the option you would
have recommended, record it as a decision in the plan with its cost, and
go on. Every such decision is listed for Doug in the final reply, so he
can reverse any of them after the big test.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires, then proceeds without waiting. Open every
reply with the local time from `date`. Keep a task list (the global Reply
Format standard): it is the only sign of progress while work runs.

**What still needs Doug, and is not a question:** a tool permission prompt
is the harness's, not yours; if one appears, Doug answers it. If a step is
refused outright (a classifier or a permission denial), do not retry it
another way: record it as owed, with the exact command for Doug to run,
and carry on with everything that does not depend on it.

### Working beside another session

Another session has worked in this checkout during every phase so far, and
the two share one git index.

- Before choosing a version number, read `git log`, the working tree's
  `pyproject.toml` and the top of `CHANGELOG.md`; take the next free one.
- **Before staging, run `git status --short`.** A file another session has
  edited and not committed (`CHANGELOG.md`, `CLAUDE.md`, `OPEN-ITEMS.md`,
  `pyproject.toml` and `uv.lock` most often) is never staged whole: write
  the index copy from `git show HEAD:<file>` plus your change (`git
  hash-object -w`, then `git update-index --cacheinfo`), and make the same
  change in the working tree.
- Check right before each commit that your staged lines are still staged;
  audit every commit with `git show --stat` and, on shared files, `git
  show --word-diff`. If your commit took in another session's lines, say
  so in the final reply; do not rewrite the commit.
- **Never push.** Doug pushes (root `CLAUDE.md` conventions).

## Read first, in full

- `prds/home-page-plan.md`: rulings 1 to 9 are settled; do not re-open
  them. This session builds § 8's phases 5, 6 and 7, to § 6 (Chapter
  News), in the look of § 5.
- `prompts/home-page-phase5-prompt-v0.1.md`: its reading list (the
  `espo-crm-changes` skill, the CRM update runbook and its twelve traps,
  `migrate_event_schema.py`, CBMRichText and `core/inline_images.py`,
  `events/visibility.py`, the settings registry and its fixture) applies
  here unchanged. Read everything it lists.
- `OPEN-ITEMS.md` #89, including part (8), the fixed header bar, and #87,
  the Association's owed baseline re-capture.
- For phase 7: the root `CLAUDE.md` "Email" section (two sending
  identities, the shared mailbox, `OPS_MAILBOX`), `core/gmail.py`, the
  worker's periodic jobs in `worker.py` (one with a weekly or daily
  schedule, and how a worker switch reports itself on Feature readiness),
  `core/sandbox_addresses.py` (the Association's training addresses must
  never be mailed), and `[[gmail-delegation-needs-licensed-mailbox]]`.

## The work, in order

Each numbered part is its own release: its own version, `CHANGELOG.md`
entry and commit, with the full test suite passing before the commit.

1. **The fixed header bar** (#89 part 8; Doug, 11-19-26: "If there is a
   scroll bar, the menu at the top (sign out row) should never
   disappear"). On the new home page the white bar with the applications,
   the text size and Sign out stays at the top while the page scrolls.
   Check it at the three text sizes (the bar is inside the zoomed page),
   on a narrow screen with the Applications menu open, and with the
   Directories menu open. Small; do it first.
2. **Phase 5, Chapter News core**: the CRM build (below), then the News
   section, past news, the Chapter News page, the visibility rule, the
   publisher team setting. Behind a new switch `CHAPTER_NEWS`, off.
3. **Phase 6, read reports** on the Chapter News page (§ 6.2): for each
   item, how many of its audience have read it out of how many, and who
   has not; for an item to acknowledge, who acknowledged and when.
4. **Phase 7, the weekly digest** (§ 6.3, § 8): a worker job, switch
   `NEWS_DIGEST`, off, that emails each member with unread items one list
   from the shared mailbox (`OPS_MAILBOX`), items to acknowledge always
   included, nothing to a member with nothing unread; the member's opt-out,
   the preference `news.digest`, set from the News section. **Also a "Send
   me a test digest" action on the Chapter News page** that sends the
   publisher's own digest to the publisher at once, so the big test needs
   no waiting for the weekly hour.

### The CRM build (phase 5)

Write the handoff `cchapternews-entities-crm-handoff.md` in Entity Manager
vocabulary and an idempotent build script in the pattern of
`scripts/migrate_event_schema.py`, dry run by default.

**Doug's authorization for this session (11-20-26), and its limits:** run
the script's apply against **the Business Mentors Association's CRM only**
(`--env-file ~/.config/cbm-bma/bma.env`; the script must refuse any other
CRM, as `scripts/sandbox/targets.resolve` does), after its dry run prints
exactly the two entities, their fields and links, and nothing else. Then
verify the build in `GET /Metadata` as the org-wide key **and** as a real
non-administrator (`joe.mentor@bma.test`), and add the role grants the
feature needs on the Association the same way (as a script, dry run
first). **Never apply anything to crm-test, Cleveland's production or a
chapter's CRM.** If the apply is refused by a permission prompt Doug does
not answer, follow "What still needs Doug" above.

## Decisions taken in advance

These are the answers this session's stopping point (a) would have asked.
Use them; record each in the plan's § 8 as decided at Doug's direction
of 11-20-26, with its cost. Change one only when the code or the CRM proves
its premise false, and then say so in the final reply.

1. **One release per phase**, as listed above. Cost: four version numbers
   in one session.
2. **Audience by team.** `Team` is not customizable on the Association
   (`scopes.Team.customizable` is false, read 11-20-26). First try the
   planned many-to-many link from `CChapterNews` to `Team` through the
   API on the Association and read it back; if EspoCRM refuses or the link
   does not read back, use a multi-select field `audienceTeams` whose
   options are the CRM's team names, kept in step by the build script, and
   say which was built. Cost of the fallback: a team renamed later needs
   the options updated.
3. **Who reads and writes in the CRM.** Members read news and write
   receipts under the org-wide key (§ 6.4); **publishers also write items
   under the org-wide key**, gated by the publisher team in this
   application, with every action in `core/action_log.py` naming the
   publisher. Only the API role needs grants; no member or publisher role
   changes. Cost: the CRM's own history names the API user, not the
   publisher; the action log is where the publisher is named.
4. **Who publishes**: `NEWS_PUBLISH_ALLOWED_TEAMS`, default System
   Management Team. On the Association its only member is Doug's
   administrator account (read 11-20-26), and administrators pass every
   gate anyway. Cost: no one but Doug can publish on the test system until
   a team member is added.
5. **Where publishing lives**: its own application, **Chapter News**, at
   `/news/`, with a tile and a stable named tab, shown only to publishers
   (§ 6.2). Read reports are a tab or a column of that page.
6. **Images in a news body**: inline attachments on `CChapterNews.body`
   through `core/inline_images.py`, shown to members through an
   application proxy read under the org-wide key, refused for an item the
   member may not see (the visibility rule decides, in the same words as an
   unknown id).
7. **Expired items to acknowledge** stop prompting and leave the News
   section (§ 6.3); in past news an unacknowledged expired item says
   "Not acknowledged".
8. **The reads**: `GET /api/portal/home/news` for the section and one for
   past news, the news items kept for the whole application for 60 seconds,
   and dropped at once in this process when a publisher publishes, edits or
   withdraws; a member's receipts read per request. Cost: another web
   process can show a withdrawn item for up to a minute.
9. **The News section's place**: first on the page (§ 4.1), above Today and
   Needs you; with nothing unread it is one line with the **Past news**
   link. It cannot be hidden while an item to acknowledge is unread (§ 4.3).
10. **The digest's day and hour** (§ 9): Monday at 08:00 in the chapter's
    own time zone (`events/config.PUBLIC_TIMEZONE`), a System Settings
    value so a chapter can move it. The digest is sent once per member per
    week, recorded so a worker restart never sends it twice.
11. **Training addresses are never mailed.** On the Association every
    training member's address is on `bma.test`; the digest goes through
    the same guard as every other send (`core/sandbox_addresses.py`), and
    a refused address is counted and logged, never an error. The test
    digest goes to the publisher's own address.

## Throughout

- **Each part fails on its own**, wrapped in `CBMBusy.loading`; a failed
  read hides its part, never the page.
- Every new page loads `busy.js` first and `textsize.js` after it, uses the
  `{{org}}` and `{{abbr}}` tokens, never a bare `vh`/`vw`, the shared grid
  for every table, never a disabled or hidden action button.
- Every new setting gains its row in
  `tests/fixtures/setup_payload_before_integrations.json` (edit as text).
- **Look at every new screen in a browser before committing it**, with the
  stub harness (`[[sessions-frontend-stub-harness]]`) or the local app, at
  a wide and a narrow width. No phase so far was looked at before Doug's
  check; this one has no check until the end.
- **Tests** for each part: the visibility rule (audience, every status, the
  publish and expiry dates, a member who joins later), the order, dismiss
  and acknowledge (a second click finds the existing receipt), the section
  that cannot be hidden, withdraw, the publisher gate, the read report's
  counts, the digest's who-gets-what, its once-a-week record, the training
  address guard, the switches off, the CRM feature detection, the settings
  and fixture rows, the branding guard, and the fixed header.
- **Records** for each part: `CHANGELOG.md`, `OPEN-ITEMS.md` #89 (and a
  line on which CRMs hold the two entities: the Association's only), the
  plan's status line, § 6, § 8 and § 9, the root `CLAUDE.md` home page
  lines and the current-status block, a staff guide for publishers
  (`chapter-news.md`), and `SYSTEM-SETTINGS-SETUP.md` for the new settings.

## The one stopping point — the end

When all four parts are committed (not pushed), write **one big test** as a
runbook page, following Doug's step-by-step instructions standard, and
publish it. In order:

1. Raise #87 first: every item, receipt and digest record made for the
   test stays in the Association's CRM and application.
2. Push; wait for the test system's `/healthz` to show the last version.
3. At the Association's System Settings, switch on `HOME_V2`,
   `CHAPTER_NEWS` and `NEWS_DIGEST` (every field written out, as before).
4. The fixed header: as Joe Mentor at each text size, scroll; the bar
   stays.
5. As the publisher (Doug's administrator account): publish one item of
   each importance (normal, pinned, must acknowledge), one with an image,
   one with a call to action, one limited to the Mentor Team; see the live
   preview.
6. As Joe Mentor, Kitty Cat and Mark Marketing: exactly the items each
   should see, in order; dismiss one, acknowledge one, and see the
   section refuse to hide while an item waits; open past news.
7. As the publisher: the read report shows those receipts, with who has
   not read; withdraw one item and see it vanish for a member, past news
   included.
8. **Send me a test digest** and find it in Doug's mailbox.
9. Switch off what the test switched on, and say what stays.

Then end with a final reply that holds only:
- the review list: each release with its version, what it does, and
  where;
- **every decision this session took on Doug's behalf**, the advance
  defaults it kept and any it changed and why, each with its cost, so Doug
  can reverse any after the test;
- anything owed: refused steps with the exact command for Doug, and
  anything not built;
- the runbook's link, and **To continue, I need:** the big test's results.

## Change log

| Revision | Last Updated | Change |
|---|---|---|
| 0.1 | 11-20-26 01:40 | First draft, at Doug's request of 11-20-26 (phases 5 to 7 and the fixed header in one session, no user prompts, one big test). |
