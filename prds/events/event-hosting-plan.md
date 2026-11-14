# Event hosting methods — plan

Last Updated: 11-14-26 14:05 · Revision 0.1 (draft for Doug's review) — see change log at the end.

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

Zoom Meetings' registration and participant report are read from Zoom's
developer workflow pages and community answers, **not yet tried against a real
account**; step 1 of the build is that check.

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

1. **Attendance for an Other-platform event**: an uploaded export file from
   the platform, check-in by hand, or none for now.
2. **How the confirmation words a shared link**, and whether a public
   Other-platform event may be published at all under D3-1's "the
   confirmation is the ticket", since a shared link can be forwarded.
3. **Hybrid events**: whether the hosting method applies to the online half
   only (assumed).
4. **The Zoom Meetings settings a meeting is created with**: waiting room,
   mute on entry, who may share the screen — defaults to put to Doug after
   the probe.
5. **Whether one Zoom user may host a webinar and a meeting at overlapping
   times**: the overlap warning assumes not.

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
| 0.1 | 11-14-26 14:05 | Claude (Claude Code) | Draft from Doug's design discussion of 11-14-26: rulings EH1 to EH10, the comparison of hosting methods, the open points and the build order. For Doug's review. |
