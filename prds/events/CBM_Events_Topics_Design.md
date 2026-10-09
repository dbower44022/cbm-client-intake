# CBM Events — Topics: Design (Track F, F1)

Last Updated: 10-08-26 23:25 · Revision 0.2 — see change log at the end.

**Status: D1 ruled by Doug (10-08-26); awaiting his approval to build. Nothing
built, nothing applied.** The
requirements are the two F1 rulings recorded in
`CBM_Events_Finalization_Plan.md` revision 4.29, section F1 — one is Doug's
(10-08-26), one is Claude's under the two-part test. They are cited below as
*F1-n*. What earlier designs settled for the surfaces this one touches is cited
as *F2/F3 design § n* (`CBM_Events_Audience_and_Display_Design.md`) and *F4
design § n* (`CBM_Events_Presenters_Design.md`). Everything else is Claude's
design and is marked where it is a choice. The one decision (§ 11) is ruled.

**Terms used here.** A **topic** is a subject category an event carries, such
as *Finance & Accounting*. The **topic list** is the fixed set of values an
event may carry, held in the CRM as the options of one field. The **recorded
library** is the public page's list of past webinars with a recording, and the
**topic filter** is the dropdown above it that narrows the library to one
topic. The **event editor** is the Add/Edit window in Event Administration.
The **event page** means both the public page at `/webinars/{slug}` and the
member page at `/portal/events/{id}`, which share one body renderer (F4 design
§ 5).

---

## 1. What this changes, in one paragraph

An event may carry several topics instead of one (F1-2). The topic list stays
exactly what it is — ten curated values maintained in the CRM — and nobody
types a topic into an event (F1-1). The event editor's single Topic dropdown
becomes a Topics tick list; the recorded library's topic filter offers every
topic that any recording carries and shows a recording under each of its
topics; the event page's eyebrow names all of them. In the CRM this is one new
multiple-choice field on the event, `topics`, with the same ten options, and a
one-time copy of each event's existing single topic into it; the old field is
retired from the application but left in place. The code is dark until a CRM
has the new field, the F2/F3 pattern, so a push changes nothing visible until
the field is applied.

## 2. Findings that shaped the design

All verified on crm-test and in the code on 10-08-26 unless marked otherwise.

1. **`CEvent.topic` is a single enum of ten values, custom, `maxLength` 100.**
   Read as the org-wide key: *Business Fundamentals, Marketing & Sales,
   Finance & Accounting, Legal & Compliance, Operations, Technology & Digital,
   Leadership & People, Industry-Specific, Networking, Other*. crm-test holds
   five events, four with no topic and one *Business Fundamentals*. Production
   holds ten published recordings, each given a topic on 09-14-26 (from the
   repository's record, not re-read).
2. **The topic flows through seven places**, and nowhere else (every read and
   write grepped):
   - the editor's field spec (`events/config.EVENT_FIELDS`, type `enum`,
     options read live from CRM metadata);
   - the save path's empty-enum fix (`events/service._blank_enums_to_null`,
     v0.229.1), which covers `enum` fields only;
   - the public payloads, where it rides as `category` on every list row and
     on the event detail (`events/service.py`; `topic` in that payload is the
     event **title**, the Zoom and Apps-Script vocabulary, and must stay so);
   - the recorded library: `published_recordings` reads it, `recording_topics`
     derives the filter's options from the recordings, `filter_recordings`
     matches a chosen topic by exact string, and `cfg.TOPIC_ORDER` orders the
     options;
   - the staff grid's chip beside the title (`events/frontend/app.js`) and the
     grid search;
   - the reporting event reference (`events/reporting._event_ref.category`),
     rendered as the **Topic** column of the engagement Events tab
     (`sessions/frontend`) and the contact Events tab (`directory/frontend`);
   - the event page eyebrow, `category · format`, in the shared body renderer
     (`frontend/shared/event-body.js`) and the staff preview
     (`events/frontend/preview-event.js`).
   **The website's own renderer, `wp-plugin/cbm-events/assets/cbm-events.js`,
   never reads `category`** — a grep finds no use — so the calendar card and
   the library card are unaffected by the shape of that key.
3. **No report counts events by topic.** `events/reporting.py` carries the
   topic only as a label on an event reference; the programme and conversion
   reports aggregate by event, registrant and engagement, never by topic. The
   catalogued question "how is a two-topic event counted" has no surface to
   land on today; F1-2 settles it for the day one is built.
4. **The CRM's field manager accepts a new `type` on an update** — read from
   EspoCRM's source on crm-test (`application/Espo/Tools/FieldManager/
   FieldManager.php`, `update()`: `$type = $fieldDefs['type'] ?? …`). So an
   in-place change of `topic` from `enum` to `multiEnum` is *possible at the
   metadata level* through the API the applier already uses. What is **not**
   verified: a multiEnum stores a JSON array in a text column, while `topic`
   is a `varchar(100)` holding bare strings, so the rebuild's column change
   and the reinterpretation of every stored value are unproven, the Entity
   Manager screen itself never offers a type change, and the applier is
   additive-only by rule (it creates, it never alters). → Decision D1.
5. **The editor and the save path already handle a multiple-choice field.**
   F2/F3 added two (`reachChapters`, `internalTeams`): the form renders a tick
   list for type `multiEnum` with options read live, `_MULTI_FIELD_NAMES`
   sanitises the posted values against the live options, and an empty list
   posts as `[]`, which EspoCRM accepts for an optional multiEnum. A `topics`
   spec field of that type gets all of it with no new control.
6. **A field the CRM lacks is ignored on read and feature-detected in the
   editor.** Selecting an unknown attribute is silently ignored (verified
   09-29-26), so `topics` can join `PUBLIC_SELECT` at once; `live_event_fields`
   reports which spec fields the CRM has, which is how the editor shows the
   audience controls only where they exist. The same mechanism decides, per
   deployment, whether the application is on the old field or the new one.
7. **The public filter's order is a code constant that mirrors the CRM.**
   `cfg.TOPIC_ORDER` lists the ten values so the filter follows the CRM's order
   rather than the alphabet, with a drifted value appended. F1-1 makes the
   list a thing the CRM administrator changes; a value added there would sort
   last on the public page until a code change caught up. *Claude's choice:*
   order the filter by the live field's option order, keeping `TOPIC_ORDER`
   as the fallback when metadata is unavailable.
8. **Boston's CRM carries `topic` as crm-test did before this change** (built
   from crm-test's files on 09-24-26; inferred, not re-read). The plan in § 10
   applies there with Boston's release, as every Track F change does.
9. **The earlier ruling that `topic` stays single** (07-25-26,
   `cevent-entities-crm-handoff.md` § 5) anticipated this widening "as a
   one-line schema change". F1 supersedes the single-value half; the other
   half — a browse-sized, audience-worded list designed for a public filter
   rather than the 31 mentor skills — stands and is what F1-1 protects.

## 3. The field — `CEvent.topics`

| Field (stored name) | Type | What it holds |
|---|---|---|
| `CEvent.topics` | multiEnum, options = the ten topic values, in the same order | Every topic the event carries (F1-2). Empty is allowed, as the single topic was. Label **Topics**. |

The old field, `CEvent.topic`, is **retired, not removed**: after the copy of
§ 7 the application neither reads nor writes it, it leaves the editor spec,
and the CRM keeps the column and its values. Removing the field is a separate
human decision for a later handoff — the standing rule that removals are
never part of an automated change.

*Claude's choices in the shape:* a second field rather than a type change on
the first (D1); the same ten options rather than a fresh list, because the
list is ruled good (finding 9) and the copy in § 7 must map one-to-one; the
name `topics` rather than `topicList` or `categories`, because the editor
label is Topics and the public payload keeps `category` for compatibility
(§ 6).

## 4. The event editor

**Topics** replaces **Topic** in the Event group, at the same position, as the
existing multiple-choice tick list (finding 5) with the ten options read live
from `CEvent.topics`. Help text: "Every subject this event covers. The website's
recorded-webinar filter lists the event under each one. To add a subject to
the list, change the field in the CRM." No "other" box and no free-text entry
anywhere (F1-1).

**Which field the editor shows is feature-detected per deployment** (finding
6): when the live CRM has `topics`, the editor shows Topics and reads and
writes `topics` only; when it does not, the editor shows the single Topic
exactly as today. A deployment is therefore never on both at once, and a push
before the CRM change changes nothing.

**Save.** `topics` rides the ordinary event PUT; the multiple-choice sanitiser
drops a value outside the live options (fails open) and an empty list is
stored as `[]`. The old field is not written.

**Staff Overview tab.** The Event facts group lists the topics joined by ", ",
"—" when there are none. The grid chip beside the title shows every topic as
its own chip, in the field's order; the grid search matches any of them.

## 5. The public pages

**The recorded library** (F1-2). `recording_topics` collects every topic any
recording carries, across all of its topics, ordered by the live field's
option order (finding 7, fallback `TOPIC_ORDER`), a drifted value still
appended. `filter_recordings` keeps a recording when the chosen topic is **any
one** of its topics, and the keyword search looks across all of them. The
rest is unchanged: options with nothing behind them are not offered, the list
does not shift under a search, one topic hides the control.

**The event page.** The eyebrow reads the topics joined by " · ", then the
format, as `Finance & Accounting · Marketing & Sales · Online Webinar`. *Claude's
choice*: all of them rather than the first, because the eyebrow is the one
place the page says what the event is about, and a visitor who arrived by
filtering on the second topic should see it named.

**The calendar card and the library card are unchanged** (finding 2: the
website renderer never read the topic).

## 6. The API

**Public and member reads.** Every payload that carried `category` keeps it,
now holding the **first** topic in the field's order (or `""`), and gains
`categories: [...]` with all of them. Keeping `category` means nothing that
reads the Apps-Script-shaped payload breaks; the pages switch to `categories`.
`topic` in those payloads stays the event title (finding 2).

**Staff reads.** The grid rows and the event detail carry `topics: [...]`; the
`GET /fields` response reports whether the CRM has `topics`, the way it reports
the audience fields, so the editor knows which control to draw.

**Reports.** `_event_ref` gains `categories`; the Topic column on the
engagement and contact Events tabs shows them joined by ", ". No count changes,
because none counts by topic (finding 3).

**Guard tests.** The spec carries `topics` as `multiEnum` and no longer
carries `topic` once the CRM has the new field; a recording with two topics is
offered under both and matched by either; the filter order follows live
metadata and falls back to `TOPIC_ORDER`; `category` is the first topic and
`categories` is the list; the eyebrow names every topic; a deployment whose
CRM lacks `topics` behaves exactly as v0.241.2 (the existing topic tests keep
passing against the old field).

## 7. The one-time copy

`scripts/migrate_event_topics.py`, shipped in the image like the applier
(v0.241.2's lesson), dry-run by default, idempotent: for every `CEvent` whose
`topic` is set and whose `topics` is empty, write `topics = [topic]`; an event
with `topics` already set is skipped; an event with no `topic` is skipped. It
runs as the org-wide API key (its role holds `CEvent` edit all on every CRM,
read from the 08-31-26 capture) from inside the deployed web container on
production, from the repository against crm-test. It prints what it would
change, then what it changed and read back. Expected counts: crm-test 1,
production 10, Boston 0 (the last two inferred).

It runs **after** the plan of § 10 and **before** the application is relied on
for that CRM; in between, the editor already shows Topics (the field exists)
and an event opened in it shows no topics until the copy has run — minutes,
on the same change window.

## 8. Feature detection and settings

**Detection only, no switch** — the F2/F3 pattern (`CBM_Events_Audience_and_
Display_Design.md`), not the F4 one: the fallback is the exact current
behaviour, no permission changes, and the whole feature is one field. The
application reads `entityDefs.CEvent.fields.topics` through the existing
`live_event_fields` read (which already tolerates an absent field, v0.235.1):
present ⇒ `topics` everywhere above; absent ⇒ v0.241.2 behaviour on `topic`.
A failed metadata read keeps the old field (fails closed on the new one).

**Settings.** None new.

## 9. Rollout and verification

1. **Build dark**; suite green; the guard tests of § 6; the no-hardcoded-name
   and buttons-never-disabled guards cover the editor change.
2. **crm-test CRM change** with the applier from the plan in § 10: dry run
   (one field, one fingerprint), apply with `--expect`, read `topics` back as
   the org-wide key with its ten options in order. Then the copy of § 7, dry
   run and apply, and read the one copied event back.
3. **Review on crm-test as a real Marketing Admin non-admin** (Mark
   Marketing): open an event, see Topics as a tick list where Topic was, tick
   two, save, see both on the Overview and as two chips in the grid; give a
   recording two topics and confirm the public library offers both, filtering
   on either shows it, and its page's eyebrow names both; confirm there is no
   way to type a topic; confirm an event with no topic still saves. Note the
   nightly reset.
4. **Production** at the Sunday 17:00 UTC slot from inside the deployed web
   container: the plan, then the copy; the editor lights up on its own.
   **Boston** with its next release, the same two runs from the build computer.

## 10. The CRM change — plan file and handoff

The plan, kept at `scripts/plans/cevent-topics.json`, written unprefixed as
the applier requires (on a custom entity the name is stored as typed):

```json
{
  "name": "cevent-topics",
  "description": "F1 topics: an event carries several curated topics — CBM_Events_Topics_Design.md",
  "entities": [],
  "fields": [
    {"entity": "CEvent", "name": "topics", "type": "multiEnum",
     "options": ["Business Fundamentals", "Marketing & Sales", "Finance & Accounting",
                 "Legal & Compliance", "Operations", "Technology & Digital",
                 "Leadership & People", "Industry-Specific", "Networking", "Other"],
     "label": "Topics",
     "tooltipText": "Every subject this event covers. The website's recorded-webinar filter lists the event under each one. Add a subject to this list here, never on an event."}
  ]
}
```

One field, so one dry-run line and one fingerprint: the dry run against
crm-test on 10-08-26 23:45 printed exactly `create field CEvent.topics
(multiEnum)` and fingerprint **`1a404fc9c337`** (nothing applied). The applier
has created multiEnum fields with options before (`reachChapters`, 09-29-26). The handoff
document, `cevent-topics-crm-handoff.md`, is written after the crm-test dry
run so it records what actually happened, and carries the copy script's runs
beside the plan's.

## 11. Decisions for Doug

**D1 — A second field, or the first field changed in place.** Finding 4 shows
the CRM would accept `type: multiEnum` on an update of `topic`, so there are
two ways to get a multiple-choice topic:

- *A new field `topics` beside the old one, with a one-time copy* (this
  design). The applier does it with its existing additive behaviour, the copy
  is a plain record write that can be dry-run and read back, and a deployment
  whose CRM has not had the change keeps working on the old field. Cost: the
  CRM carries two topic fields until a later handoff removes the retired one,
  and anyone reading the CRM's own screens sees both — the old one labelled
  Topic and holding yesterday's value.
- *Change `topic` in place from enum to multiEnum.* One field, one name,
  nothing to retire. Cost: the applier would need a non-additive capability
  it has by rule never had; the column change and the re-encoding of every
  stored value from a bare string to a JSON array are unproven and would be
  proven on crm-test only (the nightly reset would hide a slow failure); and
  there is no fallback for a deployment mid-change, because the field the old
  code reads is the field being altered.

*Recommendation: the new field.* Its cost is a retired field left in the CRM
until a removal handoff, which is the same cost the unused `CEvent.presenters`
link already carries.

*Ruled: the new field* (Doug, 10-08-26, on Claude's recommendation). Cost
accepted: `CEvent.topic` stays in every CRM, holding yesterday's value, until
a removal handoff; staff opening an event in the CRM itself see two topic
fields until then. The design above stands as written.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.2 | 10-08-26 23:25 | Claude (Claude Code) | D1 ruled by Doug: a new `topics` field with a one-time copy, not an in-place change. Awaiting approval to build. |
| 0.1 | 10-08-26 23:40 | Claude (Claude Code) | First draft, from the two F1 requirements in the Finalization Plan revision 4.29. Nine findings verified on crm-test and in the code (notably: the topic flows through seven places and the website renderer is not one of them; no report counts by topic; the CRM's field manager accepts a type change on update, unproven below the metadata). New field `CEvent.topics` drawn in § 3, the one-time copy in § 7, plan file in § 10. One decision for Doug (D1, new field or in-place change). Awaiting review; nothing built. |
