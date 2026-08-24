# CRating — CRM build handoff

Written in **Entity Manager vocabulary** — "LEFT" means the entity whose
Relationships tab you are on. Plan: `prds/rating-engine-plan.md` (rulings of
2026-08-23). Nothing here exists yet.

**Build on crm-test first**, verify, then production.

---

## 0. What is being built and why

CBM captures recipient feedback **in-house**: a client rates a mentoring session,
an attendee rates an event, each on a short instrument scored **1–5** with one
question designated the headline. `CRating` is one submitted response.

Three decisions shape the schema, and they are why this is **one** entity rather
than three:

1. **The instrument is app-side configuration, not a CRM entity.** Questions and
   their wording are configuration; the answers are the business record.
2. **Per-question scores ride as a JSON snapshot** in `answers`, storing the
   question text *as asked*, so editing an instrument never rewrites history. The
   **headline score is a real numeric field** so the CRM can average it natively
   — that is the whole point of putting ratings in the CRM.
3. **A row is created when someone responds, not when the invitation is sent.**
   The token and the reminder schedule stay in the app's Postgres: tokens are
   secrets that do not belong in a CRM field staff can read, and a row per
   unanswered invitation would fill the entity with noise.

---

## 1. `CRating`

Administration → Entity Manager → **Create Entity**.

- **Name:** `Rating` — **type it WITHOUT the C.** EspoCRM's
  `NameUtil::addCustomPrefix()` prepends it unconditionally
  (`customPrefixDisabled` is `false` on this instance — checked in source
  2026-08-23), so `Rating` becomes `CRating` and `CRating` would become
  `CCRating`. That is exactly how the grant build produced `CCGrant`.
- **Label:** `Rating` · **Plural:** `Ratings`
- **Type:** `BasePlus`
- **Stream:** off.

| Name | Type | Notes |
|---|---|---|
| `name` | varchar | **Required** by EspoCRM. The app supplies e.g. "2026-08-23 — Session feedback" |
| `ratingScore` | int | **The headline score, 1–5.** Min `1`, Max `5`. This is the field every average is taken over — a grant's "average approval rating" is `avg(ratingScore)` across the period |
| `answers` | text | JSON: instrument key + version, and each question's **text as asked** with its score. Not hand-edited |
| `comment` | text | The respondent's free text. **The mentor sees this verbatim** (ruling below) |
| `instrumentKey` | varchar | Which instrument was answered |
| `instrumentVersion` | int | Which version of it |
| `submittedDate` | datetime | |
| `ratingStatus` | enum | `Submitted` · `Comment Redacted`. Default `Submitted` |

Field names are **not** prefixed here: `FieldManager::create()` only prefixes on
a non-custom scope, and `CRating` is custom. Type them exactly as written.

## 2. Links

The Create Link dialog's two **Name** boxes are **inverted**: the Name box under
the LEFT panel is `linkForeign` (the link created on the *other* entity) and the
one under the RIGHT panel is `link` (created on the entity you opened the dialog
from). That is read straight off the dialog's own template — the box-by-box map
is in `cgrant-entities-crm-handoff.md` §5.1, and it is worth reading once before
doing any of these. The values below are already in the correct, inverted-looking
boxes.

### 2.1 Rating → Contact (who responded)

⚠️ **Contact is a system entity, so EspoCRM blindly prepends `c` to any name
landing on it.** Type it **unprefixed** — `ratings` is stored as `cRatings`.
Typing `cRatings` yields `cCRatings`.

1. Entity Manager → **Rating** → Relationships → + Create Link.
2. LEFT panel header must read **Rating**.
3. **Type:** `Many-to-One`.
4. **RIGHT panel Entity:** `Contact`.
5. **LEFT panel Name:** `ratings`  ← unprefixed on purpose  **Label:** `Ratings`
6. **RIGHT panel Name:** `respondentContact`   **Label:** `Respondent`

**Verify:** `entityDefs.Contact.links` contains **`cRatings`** (with the `c`,
added by EspoCRM), and `entityDefs.CRating.links.respondentContact` exists.

### 2.2 Rating → Mentor Profile (who was rated)

Denormalised on purpose: a mentor's own feedback is then one query, and it is
what the read-own ACL below keys on.

1. Entity Manager → **Rating** → Relationships → + Create Link.
2. **Type:** `Many-to-One`.
3. **RIGHT panel Entity:** **CBM Member** — that is how `CMentorProfile` is
   labelled in this CRM (checked 2026-08-23), NOT "Mentor Profile".
4. **LEFT panel Name:** `ratings`   **Label:** `Ratings`
5. **RIGHT panel Name:** `mentorProfile`   **Label:** `Mentor`

*(Custom entity — no `c` prefixing here. Left empty for an event rating.)*

### 2.3 Rating → its subject (session or event)

**Required outcome:** a rating points at either a `CSession` or a `CEvent`, and
**adding a third subject later must be configuration, not a rebuild** (Doug's
ruling: "design for more later").

This section was previously written without being able to read the dialog. It
has now been verified against `Tools/LinkManager/LinkManager.php` on the running
crm-test instance (2026-08-23), and the mechanism is real:

1. Entity Manager → **Rating** → Relationships → **Create Link**.
2. **Link Type:** `Children to Parent`.
3. Leave **Foreign Entity** empty — this link type does not take one. (Source:
   the `CHILDREN_TO_PARENT` branch sets only the left-hand entity's defs.)
4. **Name** (the box that becomes the field on Rating): `parent`
5. **Label:** `About`
6. The dialog offers a **parent entity list** — set it to **Session** and
   **Event** (those are the labels for `CSession` and `CEvent`; both match their
   names here, unlike CBM Member). This is `parentEntityTypeList` in the API,
   and it becomes the `entityList` of a `linkParent` field. **Adding a third
   subject later is editing this list** — which is what makes the ruling true.

Two things to know that are easy to get wrong:

- **The foreign link name DOES get a `c` prefix here.** The prefix rule is
  `if (!$entityForeign || !$this->isScopeCustom($entityForeign))` — and for
  Children-to-Parent there *is* no foreign entity, so the condition is true and
  the prefix is applied regardless. Expect `cRatings`, not `ratings`, wherever
  the foreign link name shows up.
- **The parent entities do NOT automatically get a `ratings` panel.** The
  `CHILDREN_TO_PARENT` branch writes defs for the left-hand entity only; there
  is no right-hand half. An earlier version of this file said each parent entity
  would show a `ratings` (hasChildren) link — that was wrong. The application
  does not need one (it filters `CRating` on `parentId` / `parentType`), but if
  you want the panel on a session, add a `hasChildren` link to that entity
  separately.

**Verify:** `GET /api/v1/Metadata` must show
`entityDefs.CRating.fields.parent` with `"type": "linkParent"` and both
`CSession` and `CEvent` in its `entityList`, and
`entityDefs.CRating.links.parent` with `"type": "belongsToParent"`.

**Fallback if the dialog fights you**: two ordinary nullable `Many-to-One`
links, `session` → `CSession` and `event` → `CEvent` (left-panel Name `ratings`
in each case — see §2.1 for which box that is). It costs one CRM link per future
subject instead of a config edit. Take it rather than wrestling the dialog, and
say which way it went.

## 3. Role grants — and one of them is a rule, not a preference

| Role / team | Create | Read | Edit | Delete |
|---|---|---|---|---|
| **Mentor Team** | ❌ | **Own** | ❌ | ❌ |
| **Mentor Administration Team** | ❌ | **All** | ✅ | ❌ |
| **The org-wide API key user** | ✅ | All | ✅ | ❌ |

- **Mentor Team read-own** is how ruling 4 is enforced — a mentor sees their own
  aggregate *and* the verbatim comments, via the `assignedUser` the app stamps
  with the rated mentor's User. **No edit and no delete: the person being rated
  can never alter or remove a response about themselves.** That is the integrity
  of the whole exercise, and it is enforced here in the CRM rather than only in
  the app.
- **Mentor Administration edit** exists for exactly one purpose — redacting an
  abusive comment, which flips `ratingStatus` and leaves an `CActionLog` trail.
- **The API key creates the rows**: the respondent is a client or an attendee
  with no CRM identity, so the public rating page writes under the org-wide key,
  the same way the five intake forms create their records.
- Nobody gets delete.

Check the result on a **real non-admin mentor** — an admin bypasses ACL entirely,
which is how mentor-only bugs have stayed invisible here before.

## 4. What this does NOT need

No fields on `CSession` or `CEventRegistration`. An earlier sketch wrote a
headline score back onto the session; with `CRating` as a real entity the score
lives on the rating and the session reaches it through the parent link.
