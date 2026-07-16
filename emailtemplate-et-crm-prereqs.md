# Email Template integration (ET) — CRM prerequisites & optional field

**Status: app side shipped in v0.67.0** (template picker + server-side
rendering + attachments + Email write-back, in every compose dialog). Two
CRM-side items make it fully available: two role grants (REQUIRED for the
partner/sponsor tools) and one optional filter field (feature-gated — the
app activates it automatically when built). CRM-team handoff in the style of
`csession-calendar-field.md`. Apply on **crm-test first**; prod follows the
live verification.

## 1. Role grants (required)

The picker lists templates **as the signed-in user**, and the send-recording
write-back creates an **Email** record as them — so their role needs both
scopes. Read live from crm-test 2026-07-16:

| Role | EmailTemplate | Email | Action needed |
|---|---|---|---|
| Mentor Role | read=team | create=yes, read=own | none — already works |
| Standard User | read=all | create=yes, read=all | none |
| Marketing Admin Role | full | full | none |
| **Partner Manager Role** | **none** | **none** | **grant** EmailTemplate Read (team or all) + Email Create=yes, Read=own |
| **Sponsor Manager Role** | **none** | **none** | same |

Notes:
- With no grant the picker is simply **empty** (and the write-back reports a
  recoverable failure) — nothing breaks, but partner/sponsor managers get no
  templates and no History-panel records until granted.
- **Team-scoped visibility is the template-targeting tool**: a template
  assigned to the Partner Management Team shows only to those users. Use it
  to keep each audience's list short.
- Template standing attachments need no extra grant: the parse action clones
  them to the acting user, and Attachment carries no ACL scope of its own.

## 2. Optional — `EmailTemplate.cAppliesTo` (context filter, feature-gated)

Without this field every visible template appears in every compose dialog.
When template count grows, this multi-enum lets the session tools filter by
compose context. **The app detects it from metadata and starts filtering on
its own — no app deploy needed** (the `mentorSummary` pattern).

Standing in **Entity Manager → Email Template → Fields → Add Field**:

| Setting | Value |
|---|---|
| Type | **Multi-Enum** |
| Name | `appliesTo` (EspoCRM stores it as `cAppliesTo` — the name the app detects) |
| Label | Applies To |
| Options | `Engagement`, `Partner`, `Sponsor` — **exact spelling/case** |
| Required | No |
| Default | (none) |

Behavior once built:
- A template with **no value** shows in every dialog (safe default — nothing
  disappears when the field lands).
- `Engagement` → mentor-sessions compose; `Partner` → partner-sessions;
  `Sponsor` → sponsor-sessions. The record-less quick-compose (grid pages,
  Client/Mentor Administration) never filters.
- Place the field on the EmailTemplate detail layout so admins can set it.

## 3. Live verification (after the grants)

As a partner or sponsor manager on crm-test: open a record → Communications
→ Compose → the picker lists the team's templates; apply one → placeholders
resolved; send → the message arrives AND an Email record appears in the
recipient contact's History panel attributed to the manager. (The mentor
domain can be verified immediately — Mentor Role already carries both
grants.)
