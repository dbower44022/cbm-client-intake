# Event hosting methods — plan

Last Updated: 11-15-26 02:17 · Revision 0.6 — see change log at the end.

This plan decides how a chapter's online events are hosted: Zoom Webinars,
Zoom Meetings, a link to any other platform, or an outside host. It records
the rulings Doug made in the design discussion of 11-14-26 (13:02 to 13:36),
the open points still to settle, and the build order. Nothing in it is built
yet. It touches the Events application (`events/`, `events/CLAUDE.md`) and the
Integrations tab of System Settings (`prds/integrations-tab-plan.md` § 10,
whose Zoom wizard pilot it replaces in part).

## 1. Why

The Events application knows two hosting methods for a public online event
today: the chapter's own **Zoom Webinars** account, which the application
drives completely, and an **outside host** (rulings D3-3, D3-4), where the
public page sends people to the host to register and the application keeps
nothing. Doug, 11-14-26: "Events can use a number of different hosting
providers, not just Zoom Webinars … what functionality changes with each
option, and how do we make the system as capable as possible for each user's
meeting hosting solution?" Many chapters "would prefer to use Zoom Meetings to
avoid high costs of Zoom Webinars if they do not have a large number of
events."

Zoom Webinars is a paid add-on: about $67 to $89 a month on top of a Zoom
plan, against $14 to $17 a month for a Zoom Meetings Pro user (zoom.us/pricing,
read 11-14-26).

## 2. Terms

- **Hosting method**: how one event's online part is run. One of: Zoom
  Webinars, Zoom Meetings, Other platform, Outside host.
- **Personal join link**: a join link made for one registrant, which Zoom
  issues when the application registers that person on a webinar or a
  meeting. Under ruling D3-1 the confirmation carrying it is the ticket.
- **Shared join link**: one link for everyone, typed by staff.
- **Event host user**: the one Zoom user on the chapter's account under whom
  the application creates the chapter's Zoom events.

## 3. What each hosting method does

| | Zoom Webinars | Zoom Meetings | Other platform | Outside host |
|---|---|---|---|---|
| Who keeps the registrations | the application | the application | the application | the host |
| Join link | personal | personal | shared, typed by staff | the host's |
| Created, updated and cancelled by the application | yes | yes | no | no |
| Our confirmation and reminders carry the link | yes | yes | yes | no |
| Attendance | Zoom's report | Zoom's report (Pro and above) | open point (§ 6) | none |
| Attendee camera and microphone | off (webinar) | on (meeting) | the platform's | the host's |
| Capacity | the Webinars licence's | about 100 on Pro, more on larger plans | the platform's | the host's |

**Tried against a real account 11-15-26** (step 1, the Business Mentors
Association's Zoom Pro account, no Webinars add-on): registration on a
meeting gives each registrant a personal join link; a registrant can join
without the host when the meeting allows it; the participant report, read
about 15 minutes after the meeting ended, carries the participant's
`user_email`, which matches the registration — and **no `registrant_id`**,
so attendance is matched by email, as `events/attendance.py` already does
for webinars. The account's meeting capacity reads 100. The scopes the
Meetings integration needs (ten, besides `user:read:user:admin`):
`user:read:settings:admin`, `meeting:read:list_meetings:admin`,
`meeting:read:meeting:admin`, `meeting:write:meeting:admin`,
`meeting:update:meeting:admin`, `meeting:delete:meeting:admin`,
`meeting:write:registrant:admin`, `meeting:read:list_registrants:admin`,
`meeting:update:registrant_status:admin`,
`report:read:list_meeting_participants:admin`. They are found through the
Scopes page's Add Scopes button; the page's own search box searches only the
scopes already added.

## 4. Rulings (Doug, 11-14-26)

| # | Ruling |
|---|---|
| EH1 | **Zoom Meetings and Zoom Webinars are separate integrations** on the Integrations tab, so it is plain which a chapter has. |
| EH2 | **Zoom Meetings with registration is a hosting method**, giving each registrant a personal join link and reading attendance, as Zoom Webinars does. |
| EH3 | **Hosting methods**: Zoom Webinars, Zoom Meetings, Other platform (a typed link; the application still keeps the registrations and sends its confirmation), and Outside host (as rulings D3-3 and D3-4). Personal links are preferred where the platform gives them. |
| EH4 | **The event form offers every hosting method**, each with one line on what it means for attendees. A method whose integration is not set up is shown with the reason ("Not set up — set it up in System Settings"), never hidden. **The choice is fixed once anyone has registered.** |
| EH5 | **A default hosting method per audience**: one for public events, one for members-only events, so staff rarely choose and a chapter with both Zoom products does not set up a meeting by accident when it meant a webinar. |
| EH6 | **Guards**: an event whose capacity is above the Zoom Meetings plan's limit is refused for Zoom Meetings, with the reason; the publish confirmation names the platform in words ("This creates a Zoom Meeting, not a webinar"); the event form warns when two Zoom events would overlap. |
| EH7 | **Each Zoom integration keeps its own credentials.** The Zoom Webinars wizard asks early whether it is on the same Zoom account as Zoom Meetings, with "same account" as the default; then it uses Meetings' credentials and skips its own credential screens. |
| EH8 | **One event host user per chapter**: every Zoom event the application creates is created under one Zoom user on the chapter's account (for example events@ on the chapter's domain). When Zoom Webinars is on a separate account, that account's host is used for webinars. |
| EH9 | **Each chapter has its own Zoom account (or two).** One Zoom Webinars licence is not shared between chapters: it runs one webinar at a time, and Zoom's terms forbid sharing a login between organisations. |
| EH10 | **A mentor's own Zoom stays a personal link on their mentor profile** (`preferredMeetingProvider`, `zoomPersonalLink`, ruling of 07-24-26). Nothing about it goes in System Settings; mentoring sessions never use the chapter's Zoom account. |
| EH11 | **Every Zoom Meeting the application creates is set up like a webinar** (Doug, 11-15-26, option B of § 6 point 4): attendees join muted with cameras off; only the host may share the screen; nobody joins before the host; no waiting room, since registration already decides who holds a link; the passcode stays on, carried inside each personal join link; no automatic recording. Accepted cost: someone signed in as the event host user (EH8) starts each meeting, and makes a co-presenter co-host in the meeting so they can share (Participants → More → Make Co-Host; Zoom does not let a guest be named co-host in advance). |
| EH12 | **Attendance for an Other-platform event is marked by hand** (Doug, 11-15-26, option A of § 6 point 1), with the Registrants tab's existing Attended / No-Show marks (source Manual, never overwritten). The Follow-up tab warns before sending no-show emails for an Other-platform event where nobody has been marked yet. An upload of the platform's attendee file is not built; it can be added if a chapter asks. |
| EH13 | **A public Other-platform event may be published** (Doug, 11-15-26, option A of § 6 point 2), amending D3-1: it shows once staff have typed its shared join link, as D3-1 already requires of every public online event; the link goes only in the confirmation and the calendar file, never on a public page. The confirmation says the link is shared. Accepted cost: a forwarded link admits someone unregistered, kept out only by the platform's own controls. Draft wording, to review at step 4: "This join link is the same for everyone attending. Please keep it to yourself." |

## 5. What changes, by area

**The event record (a CRM change, crm-test first).** `CEvent.hostedBy` exists
on crm-test only (`OPEN-ITEMS.md` #80), with the values `CBM Zoom` and
`Outside host`. It becomes the hosting method: `Zoom Webinars`, `Zoom
Meetings`, `Other platform`, `Outside host`. The existing `CBM Zoom` value
maps to `Zoom Webinars`. The Zoom identifiers on the event
(`zoomWebinarId`, the registration's `zoomJoinUrl`) either serve both Zoom
methods or gain a meeting twin; the build session decides from the probe and
says which, in a handoff written in Entity Manager vocabulary.

**The Events application.**
- `core/zoom.py` gains the Meetings calls beside the Webinars ones: create,
  update, cancel, register, the participant report.
- `events/zoom_sync.py` and `events/attendance.py` act on the event's method.
- `events/visibility.py` keeps the one rule for what is shown; "needs a join
  link" applies to Other platform as it does today to Zoom (D3-1).
- The confirmation (`events/confirm.py`) sends the personal link for both Zoom
  methods and the shared link for Other platform.
- The event form shows the method choice with its default, the explanation
  line, the not-set-up reason, the capacity refusal and the overlap warning;
  publishing names the platform.

**System Settings.**
- The `Zoom` integration becomes **Zoom Webinars**; a new **Zoom Meetings**
  integration is added, each with its test and its wizard screens (plan
  `prds/integrations-tab-plan.md` § 10). The pilot's 14 screens are reworded
  for Webinars and gain the "same account as Meetings?" question.
- New settings: Zoom Meetings' credentials and host; the two defaults per
  audience; Zoom Meetings' capacity limit (default 100).
- Feature readiness and the nightly test cover Zoom Meetings.

## 6. Open points (to settle with Doug in the build session)

1. ~~**Attendance for an Other-platform event**~~ — settled as ruling EH12,
   11-15-26.
2. ~~**How the confirmation words a shared link**, and whether a public
   Other-platform event may be published~~ — settled as ruling EH13,
   11-15-26.
3. **Hybrid events**: whether the hosting method applies to the online half
   only (assumed).
4. ~~**The Zoom Meetings settings a meeting is created with**~~ — settled
   as ruling EH11, 11-15-26. Members-only events get the same settings for
   now (decided in the build session, Doug may change it); editable settings
   in System Settings are not planned. The co-host feature must be on in the
   chapter's Zoom account: the probe reports `in_meeting.co_host` from
   v0.332.2, and the integration test should check it.
5. ~~**Whether one Zoom user may host a webinar and a meeting at overlapping
   times**~~ — decided in the build session 11-15-26, not a ruling: Zoom
   lets one user host one meeting or webinar at a time (Zoom's
   documentation, not tried), and EH11 has the host start every meeting, so
   the overlap warning (EH6) counts any two Zoom events under the same event
   host user, webinars and meetings alike, from 30 minutes before each start
   (hosts open early) to its end. It warns; it never refuses.

## 7. Build order and stopping points

1. **Probe Zoom Meetings, read-only, then one real test meeting.** Extend
   `scripts/probe_zoom.py`: the user's plan type, creating a meeting with
   registration, adding one registrant, reading their join link, reading a
   past meeting's participant report, deleting the test meeting. **Stop**:
   report what Zoom actually does, and settle § 6's points 4 and 5.
2. **The integrations split** on System Settings: Zoom Webinars and Zoom
   Meetings, credentials per EH7, the event host user (EH8), the defaults per
   audience (EH5) and the Meetings capacity limit as settings, tests, wizard
   screens (drafted, then reviewed by Doug, as the Zoom pilot was). **Built
   by the Integrations tab build** (its phase 9, `prompts/integrations-tab-*`),
   not by the event-hosting session, because it is the same code; the
   event-hosting session waits for it before step 4. **Stop.**
3. **The CRM change** for the hosting method: a handoff and the plan file for
   `scripts/apply_crm_plan.py`, applied to crm-test only. **Stop.**
4. **Zoom Meetings in Events**: create, update, cancel, register, attendance;
   the confirmation for both Zoom methods; Other platform's registrations and
   confirmation (with § 6's points 1 and 2 settled). **Stop.**
5. **The event form**: the choice, the defaults per audience, the
   explanations, the guards. **Stop.**
6. **The live check on crm-test** with a real Zoom Meetings account, from a
   runbook page, then production and the chapters at the Sunday slot.
   **Stop.**

Everything is built dark, behind a switch per new capability, as the rest of
the Events work is.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.6 | 11-15-26 02:17 | Claude (Claude Code) | Ruling EH13 (Doug, § 6 point 2, option A): a public Other-platform event may be published, its shared link only in the confirmation. |
| 0.5 | 11-15-26 02:14 | Claude (Claude Code) | Ruling EH12 (Doug, § 6 point 1, option A): attendance for Other platform marked by hand, with a warning before no-show emails. |
| 0.4 | 11-15-26 02:12 | Claude (Claude Code) | Step 3 done on the Business Mentors Association's CRM, the test system (Doug, 11-15-26), not on crm-test: `cevent-hosting-method-crm-handoff.md`. The Zoom ids serve both Zoom methods; `CBM Zoom` stays stored, shown as Zoom Webinars. |
| 0.3 | 11-15-26 01:40 | Claude (Claude Code) | Ruling EH11 (Doug, § 6 point 4, option B): webinar-like meeting settings. § 6 point 5 decided in the build session: the overlap warning counts webinars and meetings under one host user. |
| 0.2 | 11-15-26 01:25 | Claude (Claude Code) | Step 1 done: § 3 records what Zoom Meetings did on the Association's account 11-15-26 (personal join links, attendance matched by email, capacity 100, the ten scopes). § 6 points 4 and 5 put to Doug. Doug approved the plan and the build prompt by running it, 11-14-26. |
| 0.1 | 11-14-26 14:05 | Claude (Claude Code) | Draft from Doug's design discussion of 11-14-26: rulings EH1 to EH10, the comparison of hosting methods, the open points and the build order. For Doug's review. |
