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

- **Name:** `CRating` · **Label:** `Rating` · **Plural:** `Ratings`
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

## 2. Links

The Create Link dialog's two **Name** boxes are **inverted**: a panel's Name
defines the link that *points at that panel's entity*, so it is stored on the
**other** side. The values below are already in the correct boxes.

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
3. **RIGHT panel Entity:** `Mentor Profile` (`CMentorProfile`).
4. **LEFT panel Name:** `ratings`   **Label:** `Ratings`
5. **RIGHT panel Name:** `mentorProfile`   **Label:** `Mentor`

*(Custom entity — no `c` prefixing here. Left empty for an event rating.)*

### 2.3 Rating → its subject (session or event)

**Required outcome:** a rating points at either a `CSession` or a `CEvent`, and
**adding a third subject later must be configuration, not a rebuild** (Doug's
ruling: "design for more later").

The EspoCRM mechanism for that is a **parent** field (`linkParent`) whose entity
list is editable afterwards — `CEvent` already carries one, so the pattern is
present in this CRM. Create the link on **Rating** as **Children to Parent**,
named `parent`, then set its **Entity List** to `CSession` and `CEvent` in Field
Manager. A third subject is then adding an entity to that list.

**Verify before moving on**, because this is the one step whose dialog I could
not read: `GET /Metadata` must show `entityDefs.CRating.fields.parent` of type
`linkParent` with `CSession` and `CEvent` in its `entityList`, and each of those
entities must show a `ratings` (hasChildren) link back.

**If Children-to-Parent proves awkward in the dialog**, the fallback is two
ordinary nullable `Many-to-One` links — `session` → `CSession` (LEFT Name
`ratings`) and `event` → `CEvent` (LEFT Name `ratings`). It costs one CRM link
per future subject instead of a config edit. Take the fallback rather than
fighting the dialog; tell me which way it went and the app follows.

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
