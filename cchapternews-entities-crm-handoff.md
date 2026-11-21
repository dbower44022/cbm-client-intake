# Chapter News — CRM handoff: `CChapterNews` and `CChapterNewsReceipt`

Last Updated: 11-21-26 01:45 · Revision 1.1 — change log at the end.

**What this adds.** Two record types for Chapter News (plan
`prds/home-page-plan.md` § 6.4, rulings 4 to 6): a **Chapter News Item**,
which publishers write in the application, and a **Chapter News Receipt**,
one member's Dismissed or Acknowledged on one item. Additive only: nothing
existing changes.

**Where it is applied.** Only the Business Mentors Association's CRM, on
11-20-26, by the build script below (Doug's authorization for that session).
crm-test, Cleveland's production and the chapters are not built and need
Doug's ruling first; the script refuses them until `ALLOWED` in it is
extended. Status per CRM lives in `OPEN-ITEMS.md` #89, never here.

**How to apply.** By the script, not by hand. It reads
`crm-plans/chapter-news.json`, fills the audience field's team names from the
CRM's own teams, applies the plan through `scripts/apply_crm_plan.py`'s
applier (which reads every change back), and grants the org-wide API key's
role:

```
PYTHONPATH=. uv run python scripts/migrate_chapter_news_schema.py --env-file ~/.config/cbm-bma/bma.env
```

The dry run prints the plan and a fingerprint; `--apply --expect
<fingerprint>` applies exactly that. Then check, read-only, as the
application's key and as a real non-administrator (the password is typed at
the prompt):

```
PYTHONPATH=. uv run python scripts/check_chapter_news_build.py --env-file ~/.config/cbm-bma/bma.env --as-user joe.mentor@bma.test
```

## 1. The record types, in Entity Manager terms

Administration → Entity Manager → Create Entity, twice. Type the **Name
without a C**: EspoCRM adds it (typing `CChapterNews` would build
`CCChapterNews`).

| Name typed | Stored as | Type | Label (singular / plural) | Stream |
|---|---|---|---|---|
| ChapterNews | `CChapterNews` | Base | Chapter News Item / Chapter News | off |
| ChapterNewsReceipt | `CChapterNewsReceipt` | Base | Chapter News Receipt / Chapter News Receipts | off |

## 2. Fields on Chapter News Item (`CChapterNews`)

Entity Manager → Chapter News Item → Fields → Add Field. The names are stored
exactly as typed (custom record type). **Never tick Read-only**: the
application writes every field, and a Read-only field drops every API write
with HTTP 200.

| Name | Type | Settings |
|---|---|---|
| summary | Text | Max length 500, rows 2 |
| body | Wysiwyg | — |
| status | Enum | Draft, Published, Withdrawn; default Draft; audited |
| publishAt | Date-Time | — |
| expiresAt | Date-Time | — |
| importance | Enum | Normal, Pinned, Must acknowledge; default Normal |
| audienceTeams | Multi-Enum | Options: every team's exact name (see below) |
| ctaLabel | Varchar | Max length 60 |
| ctaUrl | Url | — |

**Why audience is a multi-select of team names, not a link to Team.**
EspoCRM refuses any relationship to Team, because Team is not customizable
(`LinkManager` throws "Entity type 'Team' is not customizable"; read on the
Association's CRM 11-20-26). The build script keeps the options in step with
the CRM's teams: run it again after adding a team. A team renamed later
keeps its old name on the items that carry it.

## 3. Fields and relationships on Chapter News Receipt (`CChapterNewsReceipt`)

| Name | Type | Settings |
|---|---|---|
| action | Enum | Dismissed, Acknowledged; default Dismissed |
| actedAt | Date-Time | — |

Two relationships, each **Many-to-One from Chapter News Receipt**. In the API
there is no inversion: `link` is stored on the receipt. If this is ever done
in the Create Link dialog instead, read the root `CLAUDE.md` trap first — the
dialog's two Name boxes invert.

| Link on the receipt | Points at | Link on the other side (stored as) |
|---|---|---|
| `news` (Label "News item") | Chapter News Item | `receipts` |
| `member` (Label "Member") | User | `cChapterNewsReceipts` (User is not custom, so EspoCRM adds the c) |

The pair of item and member is kept unique by the application, which looks
for an existing receipt before it makes one.

## 4. Role grants

**CustomAppAPIRole** (the org-wide key): Chapter News Item and Chapter News
Receipt — create yes, read all, edit all, delete no. No other role changes:
members read news and write their receipts through the application under the
key, and publishers write items under the key, gated in the application by
`NEWS_PUBLISH_ALLOWED_TEAMS` (decision 3, 11-20-26; default Marketing Admin
Team since 11-21-26). The CRM's own history
therefore names the API user; the application's action log names the
publisher.

## 5. Check it landed

- `GET /Metadata` → `entityDefs.CChapterNews` and `entityDefs.CChapterNewsReceipt`
  carry every field above, and `entityDefs.CChapterNewsReceipt.links.member.entity`
  is `User`.
- As the org-wide key, `GET /CChapterNews?maxSize=1` and
  `GET /CChapterNewsReceipt?maxSize=1` answer 200 (a 403 means the grant is
  missing).
- `scripts/check_chapter_news_build.py` does both, and the metadata read as a
  non-administrator.

## Change log

| Revision | Last Updated | Change |
|---|---|---|
| 1.1 | 11-21-26 01:45 | The publishers' default team is now Marketing Admin Team (v0.359.4); no CRM change. |
| 1.0 | 11-20-26 02:12 | Written with the build; applied on the Business Mentors Association's CRM the same day. |
