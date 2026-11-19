# Kickoff prompt — the home page, phase 4: At the chapter

Last Updated: 11-18-26 22:50 · Revision 0.1 — see change log at the end.

**Draft for Doug's approval.** Written 11-18-26 after phase 3 (v0.349.0,
Needs you) was built and committed, **before its stop 3**. Do not start
this phase until stop 3 has passed (`OPEN-ITEMS.md` #89; runbook
https://claude.ai/artifact/B5LwGJK72qAHv7RwtGBqhA). Start a fresh Claude
Code session rooted in `~/Dropbox/Projects/cbm-client-intake`, tell it to
read this file, and tell it to follow everything below the line.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
two stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

**First, confirm stop 3 passed.** Read `OPEN-ITEMS.md` #89 and the plan's
§ 8 phase 3 line. If they do not say stop 3 passed, stop and ask Doug
whether it has, before anything else.

**Another session may be working in this checkout at the same time.** Before
choosing a version number, read `git log`, the working tree's
`pyproject.toml` and the top of `CHANGELOG.md`, and take the next free one;
never take numbers from this prompt. Commit only this phase's files, staged
and committed in one step, then audit with `git show --stat`. If another
session commits between your read and your commit, check that your
`CHANGELOG.md` entry still sits above theirs.

Read, in full, before any code:

- `prds/home-page-plan.md`: the plan. **Rulings 1 to 9 are settled; do not
  re-open them.** This phase builds § 8's phase 4, to § 4.1's At the
  chapter line, in the look of § 5. § 9 names one question for this phase
  (a data source for presenter-wanted asks).
- `prompts/home-page-mix-mockup.html`: the At the chapter block as sample
  data (lines 145 to 172): "Clients served this year 312 · yours 9",
  "Sessions held this year 1,487 · yours 41", upcoming workshops, and
  "Where you're needed" (a presenter wanted, a call list).
- The root `CLAUDE.md`: "Portal + authentication" (the new home page lines
  and endpoints), "Analytics" (the org-wide key for system metrics, the
  cache, record-scoped metrics never cached), "Marketing Management",
  "Events & Webinars" (`events/visibility.py` is the one rule; never
  re-filter the rail), "Conventions" (busy.js, textsize.js and no bare
  `vh`/`vw`, buttons never disabled or hidden, the shared grid), and the
  "A 403 and a 404" gotcha.
- Phases 1 to 3's code, which this phase extends: `portal/router.py`
  (`_home_sections`, `_member_records` and its 20-second shared read,
  `home_needs`), `portal/needs.py`, `portal/frontend/home.js` (`moveIn`,
  `chapterSettled`, the frames), `portal/frontend/app.js` (`renderHomeV2`,
  `loadPortalDashboard`, `loadEventsRail`), `home.css`,
  `frontend/shared/panel.css`.
- `analytics/router.py` (`GET /analytics/api/portal`, `_system_client`,
  `_can_view_page`), `analytics/dashboard.py` (the `system-overview` page
  the portal shows today), `analytics/computed.py`, `analytics/store.py`
  (`analytics_cache`) and `analytics-guide.md`: where the chapter's numbers
  already come from, and who may see them today (the analytics view team
  only).
- `campaigns/CLAUDE.md` and `campaigns/calls.py` (`may_call`,
  `may_call_any`, the Running call campaigns, ruling 114 and ruling 36),
  plus `portal/router._campaign_calls_tile`: the source for "Where you're
  needed".
- `events/CLAUDE.md` and `events/service.portal_calendar`: the Upcoming
  events panel already shows the workshops (Doug, 11-18-26).
- `OPEN-ITEMS.md` #89.

## Scope of this phase

Fill the At the chapter frame, still dark behind `HOME_V2`:

1. **The chapter's numbers for the year beside the member's own** (§ 4.1;
   the mockup's "312 · yours 9"). Every member sees the chapter's figure;
   a member with mentoring work also sees their own.
2. **Where you're needed**: the open asks a member can act on. Running call
   campaigns that name one of the member's teams, each with what is left
   to call and a link that opens the Calls tab (`/campaigns/#calls`) in its
   stable named tab. A presenter-wanted ask has no data source and is left
   out until one exists (plan § 8).
3. **Each part fails on its own**: a part whose read fails is left out
   with a logged warning; the panel says one line if the whole read fails,
   never the page. Wrapped in `CBMBusy.loading`.
4. **Tests**: each number's rule, the member's own figure (co-mentored
   engagements included, as Needs you counts them), who sees what, the
   asks' team rule, a failing part, the switch off, the branding guard.
5. **Records**: version bump and `CHANGELOG.md`; `OPEN-ITEMS.md` #89; the
   plan's status line, § 4.1, § 8 and § 9; the root `CLAUDE.md` home page
   lines if an endpoint is added; `analytics-guide.md` if the portal
   dashboard's place changes.

Out of scope: Chapter News (phases 5 to 7), any write from the home page
other than Join (ruling 1), changing the Analytics application itself, and
a presenter-wanted data source.

## Stopping point (a) — before building

Put to Doug, each as one question with options, their costs, and a
recommendation, then stop. **Verify each premise against the code or the
Association's CRM first** (read-only), and name what you verified.

- **Which numbers**: the mockup's two (clients served, sessions held), or
  others the CRM holds (hours mentored, new engagements, active mentors).
  Name how each is counted, from which entity and status, so "clients
  served" has one meaning, and whether Analytics already has a metric for
  it.
- **Which year**: the calendar year, a fiscal year (and if so, a System
  Settings value for its first month), or the last twelve months, which is
  what the portal's analytics page uses today.
- **Who sees the chapter's numbers**: every member, read under the org-wide
  key as an aggregate (the Mentors directory's availability is the
  precedent), or only the analytics view team, as today. Name what a
  mentor could learn from an aggregate that they cannot see now.
- **The member's own figure**: for whom it shows (mentors only, or anyone
  with sessions), and whether co-mentored engagements and sessions count.
- **The analytics dashboard already in At the chapter**: keep it below the
  numbers, replace it with the numbers and a link to Analytics, or move it
  into its own panel. Name what an analytics viewer loses with each.
- **Upcoming workshops**: the Upcoming events panel already shows them
  (Doug, 11-18-26). Leave them out of At the chapter, or show the next one
  or two as a line. Recommend from what the two panels side by side
  already show.
- **Where you're needed**: which campaigns count (Running call campaigns
  naming the member's team, the same rule as the Calls tab), what number
  each shows (calls left in total, or the member's own), and whether a
  Marketing Admin member, who already sees every campaign, gets the asks.
- **The read and its cost**: one new endpoint, or the existing analytics
  portal read extended. Name the CRM calls per sign-in (the `timing` log
  line on the Association is the measure: phase 2's read is 4 calls, phase
  3's adds one) and whether the chapter's figures, being the same for every
  member, are cached for the whole application and for how long.

Show the answers on one rendered screenshot of the filled panel with sample
data if that settles them faster than words.

## Stopping point (b) — after building

Commit. Then write Doug the check as a runbook page, following his
step-by-step instructions standard: push; switch `HOME_V2` on at the
Association's System Settings; sign in as Joe Mentor and compare each
chapter number and each of his own figures with the CRM or Analytics (say
which list in the CRM, or which Analytics panel, proves each one); open
each ask's link and see it land on the Calls tab; sign in as Kitty Cat and
as Mark Marketing for what each sees; switch `HOME_V2` off. Raise the
Association's owed baseline re-capture (#87) first if it is still owed.
Close the phase only after Doug's check (plan § 8, stop 4).

## Change log

| Revision | Last Updated | Change |
|---|---|---|
| 0.1 | 11-18-26 22:50 | First draft, written after phase 3 was built and before its stop 3. |
