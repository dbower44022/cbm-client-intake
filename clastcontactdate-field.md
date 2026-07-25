# Last Contact Date — CRM field + auto-update behavior

Doug's request (2026-07-25): a real, auto-maintained "Last Contact Date" on
records, shown in the grids/detail, and advanced whenever CBM contacts the
record — **an outbound email is sent from the record, or a session is recorded
on it.**

## The CRM fields (already built — verified on crm-test 2026-07-25)

| Entity | Field | Type | Notes |
|--------|-------|------|-------|
| `CEngagement` | **`lastContactDate`** | **datetime** | NEW field for this feature. |
| `CPartnerProfile` | `lastContacted` | date | EXISTING field — reused (no new field). |
| `CSponsorProfile` | `lastContacted` | date | EXISTING field — reused. |

Only `CEngagement.lastContactDate` is new. Partners & funders reuse the
`lastContacted` field they already had (and already show on their grids +
Overview since v0.154.0).

**Prod parity — the one thing to confirm:** `CEngagement.lastContactDate`
(datetime) must exist on the **production** CRM as well as crm-test (the app
selects it in the mentor grid + Referred Clients tab, so a missing field would
break those reads). Doug reported the fields are already created; this note is
the checklist item to re-confirm on prod before/after deploy.

## How the app maintains it (`sessions/`)

- Config: `DomainConfig.last_contact_attr` / `last_contact_type`
  (`sessions/config.py`) — the field name + whether to store a date or a
  datetime per domain (mentor = `lastContactDate`/datetime; partner + funder =
  `lastContacted`/date).
- Engine: `service.touch_last_contact(cfg, client, parent_id, when)` — writes
  the field **advance-only**: it never moves the date backward, and it skips a
  date in the **future** (a scheduled-but-not-yet-held session is not a contact
  yet). Runs as the signed-in user (their ACL applies) and is **best-effort** —
  any failure is logged and swallowed, so it never fails the email/session it
  rode in on.
- Triggers:
  - **Session recorded** — `create_session` and `update_session` call
    `touch_last_contact` with the session's `dateStart` (the meeting date).
    Recording a past/today session advances the date; a future scheduled session
    is skipped; marking a scheduled session Completed later advances it then.
  - **Outbound email** — the record's Communications-tab send
    (`POST /{slug}/api/records/{id}/messages`) advances the field to **now**
    after a successful send. Quick-compose / My Email / info@ replies are not
    tied to one of these records, so they don't touch it.

## Where it shows (all config-driven — no per-field UI code)

- **Referred Clients** tab (partner) — the "Last Contact" column.
- Mentor **Client Management** grid — a "Last Contact" column.
- Engagement **Overview** rail — a "Last contact" fact (renders "—" when empty).
- Partner & funder grids + Overview already show "Last Contacted" (v0.154.0).

The field is **read-only in the app** (excluded from the engagement Details edit
form — `sessions/details._ENTITY_EXCLUDED`) because it is auto-maintained; staff
who need to correct it can do so in the EspoCRM UI.
