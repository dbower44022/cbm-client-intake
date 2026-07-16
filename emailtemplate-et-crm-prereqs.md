# Email Template integration (ET) — CRM prerequisites

**Status: app side shipped in v0.67.0** (template picker + server-side
rendering + attachments + Email write-back, in every compose dialog). One
CRM-side item makes it fully available: two role grants (REQUIRED for the
partner/sponsor tools). Context filtering needs **no build at all** — it
rides the native template categories (§2). Apply on **crm-test first**; prod
follows the live verification.

**Important: EmailTemplate is NOT in Entity Manager.** It's a system entity
(`customizable: false`), so it never appears in Administration → Entity
Manager and cannot take custom fields through the UI. Everything below uses
the places it DOES appear: the **Roles** scope table (listed as "Email
Templates") and the **Email Templates** admin page itself
(Administration → Email Templates, or the `#EmailTemplate` URL).

## 1. Role grants (required)

The picker lists templates **as the signed-in user**, and the send-recording
write-back creates an **Email** record as them — so their role needs both
scopes. In **Administration → Roles → (role) → Edit**, the scope table rows
are **"Email Templates"** and **"Emails"**. Read live from crm-test
2026-07-16:

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

## 2. Optional — context filtering via template CATEGORIES (no build)

Templates carry a native **Category** (`EmailTemplate.category` →
`EmailTemplateCategory`, the category tree shown on the Email Templates
page). The app filters the session tools' pickers by the category **name**:

- Category named **`Engagement`** → shows only in the mentor-sessions
  compose; **`Partner`** → partner-sessions; **`Sponsor`** →
  sponsor-sessions (names case-insensitive).
- **No category, or any other category name** ("Newsletters", …) → the
  template shows in every dialog. Organizational categories keep working
  normally; nothing is ever hidden by accident.
- The record-less quick-compose (grid pages, Client/Mentor Administration)
  never filters.

To activate: on the **Email Templates** page, create categories named
`Engagement` / `Partner` / `Sponsor` (only the ones you want) and assign
templates to them. No app deploy, no field build.

Note: `EmailTemplateCategory` has its own ACL scope (all/team/no). The app
reads only the category *name* riding the template rows, so the managers'
roles need no separate category grant.

## 3. Live verification (after the grants)

As a partner or sponsor manager on crm-test: open a record → Communications
→ Compose → the picker lists the team's templates; apply one → placeholders
resolved; send → the message arrives AND an Email record appears in the
recipient contact's History panel attributed to the manager. (The mentor
domain can be verified immediately — Mentor Role already carries both
grants.)
