# Public mentor pages — replacing the WordPress mentor listing with the app

**Status: PLAN — not built.**

Doug's direction (2026-08-14): **eliminate the spreadsheet and the WordPress
pages that display mentors**, and replace 100% of that functionality with app
pages the website embeds in an iframe — including selecting a mentor and
starting a **Request This Mentor** intake.

> The current process of editing data in our app, and then sending it to a
> spreadsheet and then running scripts to update the WordPress web site seems
> fragile and cumbersome. We should be able to create the same experience
> dynamically.

That is the right diagnosis. Today the chain is **CRM → spreadsheet → scripts →
WordPress posts → page**: three hops and two stale copies to display data the app
already holds. The replacement is **CRM → app → browser**.

Supersedes `prds/mentor-website-feed-plan.md` (deleted), which planned to write
the spreadsheet. That plan targeted the wrong artifact — see *What the website
actually does* below.

---

## What the website actually does

Established from public endpoints on 2026-08-13/14, no credentials involved.
**The spreadsheet is not read by the website.** The pages read a WordPress
**custom post type** called `mentor`:

- `GET /wp-json/wp/v2/mentor` — 20 published mentors.
- `/mentoring/` renders a grid client-side from that endpoint (the page ships
  the text "Loading mentors…" and offers 3-per-row / 5-per-row layouts).
- Each mentor's page is the post's permalink, `/mentor/{slug}/`.
- Post `content` is empty and `featured_media` is `0` — **every field is post
  meta**, rendered by a template.

The spreadsheet sits *upstream*, feeding those posts through scripts. Removing
the posts removes the spreadsheet's only purpose.

### The field contract, and where each field comes from

| WP meta key | Filled | CRM source |
|---|---|---|
| `first_name`, `last_name` | 20/20 | Contact |
| `title` | 20/20 | `CMentorProfile.mentorTitle` |
| `about_summary` | 20/20 | `CMentorProfile.mentorSummary` — **NOT BUILT** |
| `about_complete` | 20/20 | `CMentorProfile.aboutMentor` |
| `areas_of_expertise` | 20/20 | `areaOfExpertise` + a description map — **see gap 2** |
| `industry_experience` | 20/20 | `industryExperience` |
| `linkedin_profile` | 12/20 | Contact `cLinkedInProfile` |
| `photo_url` | 20/20 | all Google Drive links — **see gap 3** |

This matches the mapping already recorded in `cmentorprofile-summary-field.md`,
independently confirmed against live data.

### Slugs: solved

All **20/20** current slugs derive exactly from `first_name` + `last_name`
(lowercased, non-alphanumerics to hyphens), with **no collisions**. The app can
reproduce every existing URL, so old links redirect mechanically and **no CRM
slug field is needed**. Collisions are handled if they ever arise by appending a
disambiguator; with 20 mentors this is not a live problem.

---

## The design

### Pages the app serves publicly

| Route | What it is |
|---|---|
| `GET /mentors/` | The directory — the grid that replaces `/mentoring/`'s mentor section. Photo, name, title, short summary per card. Keeps the existing 3-up / 5-up density choice. |
| `GET /mentors/{slug}/` | The mentor page — a faithful replacement for `/mentor/{slug}/`. |
| `GET /api/mentors.json` | The data behind both. Public, cached. |
| `GET /api/mentors/photo/{id}` | Mentor photos, served from the CRM attachment. |

**The mentor page template already exists in this repo.** `/mentorprofile`
carries a verbatim copy of the live Elementor page — the `.cbm-wrap` block in
`mentorprofile/frontend/styles.css` (hero, two-column body, expertise list,
About box, bottom panel) plus its markup in `mentorprofile/frontend/app.js`,
copied from `clevelandbusinessmentors.org/mentor/mike-lawson/` on 2026-07-14 so
that mentors editing their profile see exactly what the public sees. Lifting it
into a public renderer is the single biggest accelerator here, and it makes the
"100% of current functionality" bar realistic rather than aspirational.

That shared template becomes the **one** definition of the mentor page: the
public page and the `/mentorprofile` preview render from the same source, so
they cannot drift.

### Request This Mentor

The plumbing largely exists. `forms/client_intake/` already serves
`GET /api/client-intake/mentors` — the live roster of mentors who are Active,
`publicProfile`, and accepting new clients — and the intake wizard already has an
optional **preferred mentor** dropdown bound to `requested_mentor_id`, which
already flows through to the CRM.

What is missing is only the link between them: the form reads no query
parameters today. So **Request This Mentor** becomes
`/client-intake/?mentor={id}`, and the form preselects the dropdown and shows
which mentor was chosen. That is a query-parameter read and a preselect — a small
change to `forms/client_intake/frontend/app.js`.

An invalid or stale id must fall back silently to the normal unselected form. A
visitor should never see an error because a mentor stopped accepting clients
between loading the directory and pressing the button.

### Who appears

Consistent with the existing roster rule and with the current site:
`mentorStatus == "Active"` **AND** `publicProfile == true`.

`acceptingNewClients` is **not** a visibility gate — a mentor at capacity stays
on the site, because the directory is marketing as much as it is selection.
It gates the **button**: a mentor not accepting clients shows their page without
an active *Request This Mentor* control, and says why. Per house convention the
control is not hidden — a missing button reads as a bug.

### The iframe

The app currently sets **no `X-Frame-Options` and no CSP `frame-ancestors`** (the
only header middleware is CORS), so it is framable today by accident. Make it
deliberate: send

```
Content-Security-Policy: frame-ancestors 'self' https://clevelandbusinessmentors.org
```

on the public mentor routes only — framable by the website, by nobody else.

Two mechanics decide whether this feels native or feels embedded:

- **Height.** The frame must grow with its content or visitors get a scrollbar
  inside a scrollbar, which reads as broken. The app posts its document height to
  the parent on every navigation and resize; a short snippet on the WordPress
  page applies it.
- **Deep links.** Navigating to a mentor inside the frame must be shareable. The
  app posts the current mentor slug up, and the parent reflects it in its own URL
  (`/mentoring/#robert-angart`); on load the parent passes any such fragment down.
  This is also what the retired `/mentor/{slug}/` URLs redirect to.

The intake form runs **inside the frame** as well, so a visitor never visibly
leaves the marketing site mid-flow. It is a public page with no session, so
nothing about the wizard depends on being top-level.

---

## Field coverage — the CRM must be able to *hold* every slot

The requirement is that **every slot on the page has a CRM field a mentor can
type into**. Whether a given mentor has filled it in is a content question,
handled by the readiness gate below — not a reason to hold up the build. An
export to JSON would have exactly the same empty values; that is not a property
of the delivery mechanism.

Measured against the live page, **coverage is complete** — every slot has a CRM
field a mentor can type into:

| Page slot | CRM home | Status |
|---|---|---|
| Hero photo | `profilePhoto` | ✅ exists |
| Hero name | Contact `firstName` / `lastName` | ✅ exists |
| Hero title (gold) | `mentorTitle` | ✅ exists |
| Summary paragraph | `mentorSummary` | ✅ exists (confirmed 2026-08-14) |
| LinkedIn button | Contact `cLinkedInProfile` | ✅ exists |
| Industry box | `industryExperience` | ✅ exists |
| Expertise list — labels | `areaOfExpertise` | ✅ exists |
| Expertise list — descriptions | *(not a mentor fact — see below)* | app-side |
| About box | `aboutMentor` | ✅ exists |

**There is no schema work in this plan.** `mentorSummary` — the one-sentence
paragraph under the gold ABOUT label, distinct from the About box — was built
after `cmentorprofile-summary-field.md` was written; that doc's NOT BUILT status
is stale. Confirmed 2026-08-14: the "Short summary (shown on the website)" box is
live in My Mentor Profile, and since it is feature-gated on CRM metadata, its
presence *is* the proof the field exists.

**Expertise descriptions are not a per-mentor field.** The site renders
`"Business Strategy & Planning: Planning growth and business direction"` — a
description of the *skill*, identical for everyone who selects it. It does not
belong on a mentor record, and giving it one would guarantee the drift that has
already happened: across 29 labels, 11 carry inconsistent descriptions between
mentors today, including one with a stray `"` from hand-entry. Ship **one curated
label→description map in the app**, rendered against each mentor's selected
labels. Adding or rewording a description then touches one place instead of 20
records, and the drift ends permanently.

That is the entire schema story. Everything else below is about making sure what
mentors type produces a good page.

## Publish readiness — the gate that replaces hoping the spreadsheet is right

The reliability argument for doing this dynamically is not just that there are
fewer hops. It is that **the app can refuse to publish a bad page**, which a
spreadsheet pipeline cannot. Reuse the pattern already proven in Mentor
Administration: `check_completeness` computes a status, persists it to
`recordStatus` on save *and* on view when it changed, and never overwrites a
manually-set value — so the roster self-heals rather than needing a sweep.

**Website readiness** is a second, separate computed status alongside the
existing completeness badge, because it asks a different question: not "is this
mentor record administratively complete" but "would this render as a page we are
happy to show the public."

Required to publish: a photo; a headline; a summary; at least one area of
expertise and one industry; and an About box with real content — the existing
completeness check already knows that `<p></p>` is empty, and that lesson
transfers. LinkedIn stays optional; the live site renders the button either way,
and only 12 of 20 mentors have one.

Worth checking beyond mere presence, because these are what actually make a page
look wrong:

- **Summary length.** It is a one-or-two sentence positioning line in a narrow
  column. The live examples run roughly 40–60 words; far outside that band it
  either overruns the column or leaves a hole under the gold label.
- **Placeholder text** — "TBD", "coming soon", a name typed into the headline.
- **Expertise labels outside the current enum**, which would miss the description
  map and render bare.
- **Photo shape.** The hero is a 160px circle with `object-fit: cover`; a very
  small or extremely non-square image looks broken there specifically.

### Make the preview show the holes

One change is needed in `/mentorprofile`, and it matters more than it sounds.
The preview currently *hides* empty slots:

```js
$("pvSummary").hidden = !summary.trim();     // app.js:596
```

So a mentor with no summary sees a page that looks completely fine. That is
exactly backwards for this purpose — the preview's job becomes showing them what
the public would see *and what is missing from it*. Replace hide-when-empty with
a marked gap in the slot, plus a readiness panel beside the preview listing each
problem and linking to the field that fixes it.

This is the "highlight the problem" half, and it puts the fix in the hands of the
person who owns the content.

### Where readiness surfaces

- **My Mentor Profile** — the mentor's own readiness panel, as above. They cannot
  publish a page they have not finished, and they can see precisely why.
- **Mentor Administration** — a roster-wide column, so staff can see at a glance
  who is ready and chase the ones who are not. This is the standing quality audit.
- **The public pages** — a mentor who is Active and `publicProfile` but fails
  readiness is **held back with a stated reason**, never silently dropped. Silent
  disappearance is the failure mode this whole exercise exists to end, and per
  house convention the explanation is always shown rather than the thing hidden.

Rendering stays **live**, not generated. A generated artifact is one more copy
that can go stale — the same class of problem as the spreadsheet. The readiness
check runs on the record, continuously, rather than as a build step that has to
be remembered.

## Migrating the existing content

Not a blocker, and not on the critical path — but the 20 mentors already have
good text on the website, and there is no reason to make them retype it. The WP
REST API serves all of it publicly: summaries for all 20, About text for all 20,
and photos as Drive file ids. A one-off backfill into the CRM is scriptable, and
the app already has a Drive client for the images. Do it once, then the CRM is
the only place that content lives.

---

## Phases

| Phase | What lands |
|---|---|
| **1 — Readiness + honest preview** | The website-readiness computation, the readiness panel in My Mentor Profile, the show-the-holes change to the preview, and the roster column in Mentor Administration. **This is what makes the rest safe**, and it is useful on its own — it tells you today how far from publishable the roster is, and it would already have caught the corrupted biographies described below. |
| **2 — Public pages** | `/mentors/`, `/mentors/{slug}/`, the JSON endpoint, the photo route, and the extraction of the shared page template. Behind `PUBLIC_MENTORS_ENABLED`, default off. Reviewable on crm-test against the live site side by side. |
| **3 — Request This Mentor** | The query-parameter handoff into the intake wizard and the accepting / not-accepting button state. |
| **4 — Embed** | The `frame-ancestors` header, height sync, deep-link sync, and the WordPress page change. |
| **5 — Retire** | 301 `/mentor/{slug}/` to the published page for that mentor. Unpublish the `mentor` posts, keeping them dormant as the rollback window. **Then delete the spreadsheet and its scripts.** |

Any content backfill runs alongside phase 1 rather than gating it; readiness
reports what is still owed.

Nothing the public sees changes until phase 4, and phase 1 stands on its own
merits — mentors get a profile page that finally tells them what is wrong with it,
whatever happens afterwards.

## Evidence that the current pipeline corrupts content

Not a hypothetical. On 2026-08-14 the live site was compared against the WordPress
REST payload:

**12 of the 20 published mentors have the page's own bottom-panel boilerplate
stored inside their biography field** — between 136 and 234 characters of
"Ready to Connect with {name}? Request a free, confidential mentoring session. No
fees, no contracts. Request a Session Meet All Our Mentors Browse our full team…"
appended to `about_complete`, so the text renders twice on those pages: once
wrongly inside the About box, once correctly in the panel below.

**The CRM holds the same corruption** — confirmed by Doug on his own record,
2026-08-14: `aboutMentor` contains the boilerplate, and `/mentorprofile` renders
it. So this is not damage introduced in transit. The bad text is in the system of
record, which means **rendering live from the CRM would faithfully reproduce it**
and the switch does not fix it by itself.

### The repair

The pattern is exact. Two variants, both beginning at `"Ready to Connect with
{first}?"` and running to the end of the field:

| Variant | Mentors | Length |
|---|---|---|
| …Request a Session Meet All Our Mentors | 7 | 140 chars |
| …plus "Browse our full team of experienced volunteer mentors across every industry and business stage." | 5 | 236 chars |

No other page furniture appears in any bio ("View LinkedIn" and "Request a
Mentor" are 0/20), so the rule is unambiguous: **truncate `aboutMentor` at the
first occurrence of `"Ready to Connect with"`**; everything before it is the real
biography.

Both variants start at the bottom panel's first heading and stop at different
points within it — the signature of a human selecting a region of the rendered
page and pasting it in, twice, with two different stopping points. The content was
captured *from* the website into the CRM, not authored in the CRM.

Follow `scripts/audit_assignment_stamps.py`: a read-only report by default
printing the before/after for each of the 12 records, and an explicit `--apply`
to write. `aboutMentor` is a wysiwyg field, so the cut must be HTML-aware — drop
the element containing the marker and everything after it, not a raw string slice.
Refuse any record whose remaining bio would be empty or implausibly short, and
run it on crm-test first.

### And make it permanent

"Bio contains 'Request a Session' / 'Meet All Our Mentors'" becomes a standing
rule in the readiness check. Twelve pages carried this in public for however long;
the point of the readiness gate is that the thirteenth cannot.

## The one real trade-off: search

Content inside an iframe is generally not credited to the parent page, so the
text on those 20 mentor pages would effectively leave the search index. Today
they are 20 indexed pages carrying substantial long-form biography.

If that traffic matters, the mitigation is to redirect the old `/mentor/{slug}/`
URLs to the **app's own pages** rather than to the embedded view — the app serves
real server-rendered HTML at stable URLs, so the content stays indexed, just on
`apps.clevelandbusinessmentors.org`. The embed and the indexable pages are the
same routes, so this is a redirect-target decision at Phase 5, not an
architectural one, and it can be made with whoever watches the site's traffic.
Worth deciding deliberately rather than discovering later.

## Configuration

`PUBLIC_MENTORS_ENABLED` (default off) gates the public routes. The routes mount
unconditionally and check the flag per request, so it stays overridable at
`/setup` rather than becoming boot-read. All of this is **web**-component work —
there is no worker involvement anywhere in this plan, which is itself a sign the
design is simpler than the one it replaces.

## Testing

Parity is the bar, and it is measurable: the gap report and the live WP REST
payload give a field-by-field expected value for all 20 mentors, so the app's
rendered output can be diffed against what the site shows today. Beyond that:
slug derivation for all 20; the photo route refusing a mentor who is not
published; the intake handoff with a valid id, an unknown id and no parameter;
and the not-accepting button state.
