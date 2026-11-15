# CRM handoff — an event's hosting method (event hosting plan, rulings EH1 to EH11)

Last Updated: 11-15-26 01:50 · Revision 0.1 (prepared, not yet applied anywhere) — change log at the end.

**What changes:** the existing choice field **Hosted by** on the event record
(`CEvent.hostedBy`, built by `cevent-hostedby-crm-handoff.md`) becomes the
event's hosting method. Plan `prds/events/event-hosting-plan.md` § 5; tracked
as `OPEN-ITEMS.md` #84, after #80.

- **Two options are added:** `Zoom Meetings` and `Other platform`.
- **The existing option `CBM Zoom` is kept as stored and shown as "Zoom
  Webinars".** No event record changes, nothing is removed, and the
  application keeps reading the stored value it reads today.
- **The field's tooltip is rewritten** to describe all four methods.

**Applied by the plan file, never by hand:**
`scripts/plans/cevent-hosting-method.json`. Dry-run fingerprint on crm-test,
11-15-26 01:46: **`dc0909bb8b7a`**.

| Entity | Stored field name | Type | Label | Options (stored → shown) | Default |
|---|---|---|---|---|---|
| `CEvent` | `hostedBy` | Enum | *Hosted by* | `CBM Zoom` → Zoom Webinars · `Outside host` → Outside host · `Zoom Meetings` → Zoom Meetings · `Other platform` → Other platform | `CBM Zoom` (unchanged) |

## Prerequisite

The **Hosted by** field itself must exist: `cevent-hostedby-crm-handoff.md`,
plan `scripts/plans/cevent-hostedby.json`. On crm-test since 11-12-26; not
on production, Boston or the Business Mentors Association's CRM (#80). Where
it is missing, apply that plan first; this plan otherwise fails with
"field CEvent.hostedBy not found" and changes nothing.

## Decisions taken in this handoff

- **The Zoom identifiers serve both Zoom methods; no meeting twin.** A Zoom
  meeting id has the same shape as a webinar id, and a meeting registrant's
  join link and id the same shape as a webinar registrant's (the probe of
  11-15-26, `scripts/probe_zoom.py --meetings`). So `CEvent.zoomWebinarId`
  holds a meeting's id too, and `CEventRegistration`'s join link and
  registrant id serve both; the hosting method says which Zoom product the
  id belongs to. The field's label still reads *Zoom webinar id*; renaming a
  label is cosmetic and is left for the event form step.
- **The default stays `CBM Zoom`** (Zoom Webinars). The application, not the
  CRM, sets each new event's method from the default per audience (ruling
  EH5), so the CRM default only matters for an event created in the CRM
  directly.

## Roles and layout — nothing to change

The options and labels of an existing field carry no new grant: the roles
that edit events edit it, and the **CustomAppAPIRole** reads it. Not
Read-only (ruling 40). The CRM's own event layout is unchanged.

## Order

1. **crm-test** — the dry run reads one change (above). Apply:
   `scripts/apply_plan.sh test scripts/plans/cevent-hosting-method.json dc0909bb8b7a`.
2. **The sandbox baseline** — nothing owed for the options: they live in the
   CRM's files, which the nightly reset rebuilds from. An event set to Zoom
   Meetings or Other platform on crm-test reverts overnight with its record.
3. **Production, Boston and the Business Mentors Association** — after
   `cevent-hostedby.json` on each, at a Sunday slot. Production from inside
   the web container:
   `scripts/apply_crm_plan.py scripts/plans/cevent-hosting-method.json --apply --production --expect <fingerprint from that CRM's dry run>`.
   Every CRM prints its own fingerprint on the dry run; apply only that one.

## Proof it landed

- The applier reads the options, the labels and the tooltip back (it prints
  `verified enum CEvent.hostedBy`).
- As the org key: `GET Metadata?key=entityDefs.CEvent.fields` shows
  `hostedBy.options` with all four values, and `GET I18n?scope=CEvent` shows
  `options.hostedBy.CBM Zoom` as `Zoom Webinars`.
- As a real non-admin in the Marketing Admin Team: not in the CRM, whose
  event layout does not show **Hosted by**, but in Event Administration once
  the event form step (plan § 7 step 5) is live — the method choice there
  saves each of the four values.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-15-26 01:50 | Claude (Claude Code) | Written for the event hosting plan's step 3; dry run on crm-test, fingerprint `dc0909bb8b7a`. Not applied. |
