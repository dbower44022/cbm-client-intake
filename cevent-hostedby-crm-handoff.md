# CRM handoff — an event says who hosts it (rulings D3-3 and D3-4)

Last Updated: 11-12-26 01:06 · Revision 1.0 — change log at the end.

**What changes:** one choice field on the event record (`CEvent`). Doug's
rulings D3-3 and D3-4 (11-12-26, `prds/events/CBM_Events_Finalization_Plan.md`
row D3): a partner may host an event CBM promotes, on a platform we cannot
create in our Zoom. The event says so explicitly. Chosen **Outside host**,
staff type the host's link in the Join URL on a Public online event, Zoom
webinar provisioning stands down, and the Register button sends visitors
straight to the host. Attendance is not captured for such an event.
Tracked as `OPEN-ITEMS.md` #80.

**Applied by the plan file, never by hand:**
`scripts/plans/cevent-hostedby.json`, plan fingerprint `6eb4fc2d5940`.

| Entity | Stored field name | Type | Label | Options | Default |
|---|---|---|---|---|---|
| `CEvent` | `hostedBy` | enum | *Hosted by* | CBM Zoom · Outside host | CBM Zoom |

`CEvent` is a custom entity, so the field is stored exactly as typed. Existing
events need no back-fill: the application reads an empty value as CBM Zoom,
which is how every event behaved before this field.

## Roles — nothing to change

A new field carries no field-level rule, so it follows the entity grants: the
roles that edit events in Event Administration edit it, and the
**CustomAppAPIRole** reads it. Not Read-only (ruling 40): the application
writes it.

## Layout — nothing to change

Event Administration has its own editor, so the CRM's own event screen does
not need the field. Add it to the CRM's detail layout only if staff edit events
in the CRM directly.

## Order

1. **crm-test** — done 11-12-26 01:05: `scripts/apply_plan.sh test
   scripts/plans/cevent-hostedby.json 6eb4fc2d5940`, one change, verified.
2. **The sandbox baseline** — nothing owed. The nightly reset empties a column
   newer than the baseline, and empty reads as CBM Zoom, the safe value. An
   event set to Outside host on crm-test therefore reverts overnight: finish a
   live check the same day.
3. **Production** at a Sunday slot, from inside the web container:
   `scripts/apply_crm_plan.py scripts/plans/cevent-hostedby.json --apply --production --expect 6eb4fc2d5940`.
4. **Boston** with its release:
   `scripts/apply_plan.sh boston scripts/plans/cevent-hostedby.json 6eb4fc2d5940`.

The application feature-detects the field: until a CRM has it, Event
Administration offers no Hosted by choice and every event behaves as today.

## Proof it landed

- The applier reads the field back (it prints `verified`). Done on crm-test.
- As the org key: `GET CEvent?select=id,hostedBy&maxSize=1` → 200. Done on
  crm-test 11-12-26: 200, the field reads `CBM Zoom`.
- As a real non-admin in the Marketing Admin Team, once the application
  build is live: Event Administration → an event → Hosted by → Outside host,
  type a link, save, and the event shows in the Website preview.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 11-12-26 01:06 | Claude (Claude Code) | Written for rulings D3-3 and D3-4; applied and verified on crm-test, fingerprint `6eb4fc2d5940`. |
