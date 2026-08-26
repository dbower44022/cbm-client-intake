# Phase 0 — De-Cleveland

**Status: substantially delivered.** The mechanism and the sweep shipped in
**v0.205.0–v0.206.0** and are deployed and verified on production. What remains is
a live-verification list, one decision, and one item deliberately pushed to Phase
3 — all named at the bottom of this file.

**Why it was worth doing anyway.** Nothing else can be onboarded while the product
says Cleveland, and removing hardcoded identity is a real improvement to this
codebase with zero chapters involved. It needed no feature flag, because the
safety property is that an unconfigured deployment renders byte-identical to
before.

The standing rules this phase produced — the `{{org}}` token, the
`<meta name="cbm-org">` requirement on every new page, the identifier fence around
`CBM`/`cbm-`/`--cbm-*`/`data-cbm-*`, and `CHAPTER_TOKENS_URL` — now live in the
repo's `CLAUDE.md` Conventions section, because they bind every future page
whether or not anyone is thinking about chapters. This file is the record of what
was measured and why the calls were made.

---

**Measured against the tree on 2026-08-20**, not estimated. The plan's earlier
figure ("18 frontend HTML files") counts *files* correctly and undercounts
*occurrences* by roughly two-thirds, and it misses four surfaces outside HTML
entirely — one of which sends the public to Cleveland's own legal documents.

Every item below is classified as **setting** (already parameterized in
`core/config.py`), **override** (a per-chapter value supplied at deploy or via
`/setup`), or **markup edit** (the name is baked into a file). The safety
property governing all of it: **with no chapter configuration set, every page
must render byte-identical to today.** Cleveland is the default, not a special
case, which is why Phase 0 needs no feature flag.

## 0. Brand-as-identifier — fenced off, and it stays

This is the distinction that keeps the workstream from doing damage. The `CBM`
and `cbm-` tokens below are **identifiers, not content**. They are never shown to
a user, renaming them is enormous churn for zero benefit, and a partial rename
breaks every page. **They are out of scope permanently — this is not an
unfinished job for someone to "complete" later.**

| Identifier surface | Count | Examples |
|---|---|---|
| `window.CBM*` JS namespaces | 12 | `CBMBusy`, `CBMDateTime`, `CBMRichText`, `CBMConversation`, `CBMEvents`, `CBMWizard`, `CBMAddress`, `CBMCharts`, `CBMQuickMail`, `CBMBirthday`, `CBMDirRender`, `CBM` |
| `--cbm-*` CSS custom properties | 52 distinct, **1223 uses** | `--cbm-navy`, `--cbm-gold`, `--cbm-surface` |
| `cbm-` class-name occurrences | **2298** | `cbm-button`, `cbm-footer__version`, `cbm-required` |
| `data-cbm-*` attributes | 4 | `data-cbm-year`, `data-cbm-version`, `data-cbm-busy`, `data-cbm-upload` |

Two of these are worse than churn — they are **contracts**. `cbm-` classes in
`wp-plugin/cbm-events/` are the class contract between the renderer and the
website's own stylesheet, guarded by a test precisely because a drift there went
unnoticed for three weeks; and `CBMEvents.config` is the object a chapter's
WordPress page configures. Renaming either breaks a live site.

**A new per-chapter attribute therefore keeps the `data-cbm-` prefix.** The
prefix names the software, not the chapter.

## 1. Settings — already parameterized, needing only a non-Cleveland default story

All in `core/config.py`. Each already reads from the environment, so a chapter
supplies its own value with no code change; what Phase 0 owes them is (a) a
default that is *derived* rather than *hardcoded to Cleveland* where possible,
and (b) a place in the per-chapter values file (Phase 3).

| Setting | Today's default | Classification |
|---|---|---|
| `ops_mailbox_name` | `"Cleveland Business Mentors"` | **setting** → should default to `organization_name` |
| `comms_internal_domains` | `"cbmentors.org"` | **setting**, per-chapter override |
| `zoom_host_email` | `"zweb@cbmentors.org"` | **setting**, per-chapter override |
| `docs_site_url` | `"https://docs.clevelandbusinessmentors.org"` | **setting**, per-chapter override |
| `events_public_base_url` | `"https://clevelandbusinessmentors.org/webinars"` | **setting**, per-chapter override |

`alert_email_from`, `gdrive_shared_drive_id`, `google_members_group` and
`app_base_url` are already Cleveland-free in code and supplied per deployment.

## 2. Locale — a fifth axis the plan did not name

Cleveland's **timezone** is hardcoded in four places, and it is not the same
thing as Cleveland's name:

- `portal/birthday.py:47` — `_LOCAL = ZoneInfo("America/New_York")`
- `assignments/service.py:942` — `ZoneInfo("America/New_York")` for the assignment stamp
- `events/config.py:72` — `PUBLIC_TIMEZONE = "America/New_York"`
- `core/zoom.py:247` — default argument
- (`comms_digest_tz` is already a setting with the same default)

A chapter outside Eastern time would show wrong calendar days on birthdays,
assignment stamps and the public events programme. **Deliberately left out of
Phase 0**, by the standard Phase 0 holds itself to: fixing this is justified
*only* by chapters that may never exist — Cleveland gains nothing. It belongs
with the per-chapter values file in **Phase 3**, and is recorded here so it is
not rediscovered as a surprise during the first onboarding.

## 3. Markup — the actual work

**18 frontend HTML files, 48 occurrences**, in three shapes:

| Shape | Count | Form |
|---|---|---|
| `<title>` | 18 | `<title>Cleveland Business Mentors — Client Administration</title>` |
| Footer | 17 | `&copy; <span data-cbm-year>2026</span> Cleveland Business Mentors. All rights reserved.<span class="cbm-footer__version" data-cbm-version></span>` |
| Body prose | 13 | headings, form labels, confirmation messages |

`setup/frontend/index.html` is the one page with a title but no footer text — it
loads `footer.js` for the year and version only. The two `events/frontend/preview*.html`
harnesses use `CBM — …` titles instead; they are developer harnesses, not shipped
pages, and are listed for completeness.

The 13 body-prose occurrences are the hardest and the most likely to be missed,
because they are **read by a member of the public**:

- `portal/frontend/index.html:17` — the portal `<h1>`
- Four public forms × "How did you hear about …?" labels
- Three public forms × the `intake__sub` lead paragraph
- Five public forms × "A member of the … team will be in touch." confirmations

## 4. Four surfaces outside HTML that the earlier count missed

| Location | What it is | Classification |
|---|---|---|
| **`frontend/shared/legal-links.js:11–15`** | **Four hardcoded Cleveland policy URLs** — client code of conduct, mentor code of ethics, terms of use, privacy policy — injected into the consent checkbox on all four consent-bearing public forms | **setting** (new) — see below |
| `directory/frontend/mentor.js:120` | Sets `document.title` in JS on the mentor profile page | markup edit |
| `core/app.py:393` | Server-rendered footer on the dev-app public form index | markup edit |
| `portal/frontend/birthday.js:176` | The birthday card's eyebrow line | markup edit |
| `forms/info_email/__init__.py:17` | `FormSpec.title = "Email to Cleveland Business Mentors"`, shown to staff in `/ops` | markup edit |
| `comms/service.py:1287` | `"company": "Cleveland Business Mentors"` on a CBM member's contact lookup result | markup edit |
| `comms/summarize.py:34` | The LLM system prompt's opening line | markup edit |
| `events/frontend/app.js:891` | A warning naming the live website | markup edit |
| `frontend/shared/tokens.css:2–10` | Header comment attributing the palette to Cleveland's staging site | comment reword |

**`legal-links.js` is the serious one.** It is the single source of truth for the
policy document URLs, its own comment says so, and every one of the four URLs
points at Cleveland's WordPress (three of them still at the *staging* host,
`cbmentostagdev.wpenginepowered.com`). A second chapter running this code would
present Cleveland's privacy policy and Cleveland's code of conduct to its own
applicants as the documents they are consenting to. That is a legal exposure, not
a branding blemish — and unlike everything else in this list, **it is worth fixing
for Cleveland alone**, since three of the four already point at a staging domain
rather than the production site.

## 5. Two names, not one — **ruled a copy bug** (Doug, 2026-08-20)

The product says **"Cleveland Business Mentors"** in 59 places in code and
**"Cleveland Business Mentoring"** in 7. The seven are not scattered: they are
*exclusively* body prose on the four public intake forms —

- `how_did_you_hear` labels on info-request, partner, sponsor, volunteer
- the `intake__sub` lead paragraph on info-request, partner, sponsor

Provenance points to a slip rather than a second brand. Commit `7cc6a8f`
("fix(volunteer): rebrand SCORE wording to Cleveland Business Mentoring on the
review step") introduced the wording, and the later partner/sponsor/info-request
forms copied the phrasing. Everywhere else the *organization* is "Mentors": the
domain is `clevelandbusinessmentors.org`, `ops_mailbox_name` is
`"Cleveland Business Mentors"`, and every footer and title says Mentors.
"Cleveland Business Mentoring" does have a legitimate separate use — it names the
**process-definition repository** (`dbower44022/ClevelandBusinessMentoring`) and
is used that way in all five markdown occurrences — but that is a repo name, not
public-facing copy.

**Doug's ruling, 2026-08-20: a copy bug. Sweep them into `{{org}}`.** So the
token vocabulary stays at one token, `organization_name`, and the seven
occurrences were replaced in v0.205.0 — the four "How did you hear about …?"
labels and the three lead paragraphs. Two parameters would have
institutionalised an inconsistency no chapter would want to reproduce.

A test now fails if the wording reappears in a frontend file, because a copied
form is exactly how it spread the first time.

**There is precedent, and it points the same way.** The v0.131.0 changelog
(2026-07-21) records the same slip in a different place — *"the PROD CRM's
Outbound Emails From Name reads 'Cleveland Business Mentoring' (with -ing) — fix
to 'Cleveland Business Mentors' … so CRM-native sends match (crm-test is already
correct)"*. So the wording has been recognised as wrong once before, in the CRM
rather than the app. That Doug-side fix was never tracked anywhere and may still
be outstanding on production; it is now in `OPEN-ITEMS.md`, because a chapter's
CRM-native sends would carry whatever that field says regardless of what the app
renders.

## 6. The logo — ruled out (Doug, 2026-08-26)

**Verified: the application contains no image asset of any kind.** No `.svg`,
`.png`, `.jpg`, `.ico`, `.webp` or `.gif` outside the vendored Jodit editor, no
`<link rel="icon">` on any page, and every hit for "logo" in the codebase is the
word *logout*. The plan's "per-chapter `tokens.css` + logo" therefore describes a
**new feature** — a header/logo slot on 18 pages, an asset-serving path, and a
sizing contract — not a find-and-replace.

**Ruled 2026-08-26: nothing now.** Chapters get colours, not marks. The favicon
was offered alongside it — there is none on any page today, which is a Cleveland
gap rather than a chapter question — and was declined in the same breath.

So this is **closed, not deferred**: "per-chapter `tokens.css` + logo" comes out
of the plan wording rather than becoming a backlog item, and Phase 0 no longer
waits on it. If a chapter ever asks for a mark, this section is the measurement
of what it would cost, and it starts from zero.

## 7. `tokens.css` — the override mechanism

162 lines, 52 custom properties, all on `:root`, all consumed through
`var(--cbm-*)`. The override mechanism is therefore already latent in the
cascade: a chapter supplies a second stylesheet defining the same properties on
`:root`, loaded **after** `tokens.css`, and it cannot break the base tokens
because it can only shadow values it explicitly names — anything it omits falls
back to Cleveland's. No `!important`, no build step, no new mechanism. What Phase
0 owes is the loading slot and the rule that a chapter override may define
**only** `--cbm-*` properties on `:root` (never selectors), plus rewording the
header comment, which currently attributes the palette to Cleveland's staging
site.

## 9. What v0.205.0 actually built

**Shipped, tested, unpushed as of 2026-08-20.** The mechanism, and the sweep of
everything it covers.

- **`ORGANIZATION_NAME`** — one setting, defaulting to Cleveland, substituted
  into the markup as the `{{org}}` token by `core/branding.py`
  **server-side, as the page is served** (`BrandedStaticFiles`). Chosen over
  extending `footer.js`'s `data-cbm-*` fill because that pattern is right for
  the version (nobody reads it at first paint) and wrong for the name: the
  browser tab would flicker and the public forms' prose would visibly repaint
  after the `/healthz` round-trip.
- **The safety property was verified, not assumed** — every page's rendered
  output was compared against `origin/main`. 14 differ by exactly one invisible
  `<meta name="cbm-org">` line; 2 (the developer preview harnesses) are
  untouched; 4 carry the one deliberate visible change in the whole phase, the
  seven "…Mentoring" words Doug ruled a copy bug (§ 5). No feature flag.
- **Three code paths read HTML directly instead of through the mount** — the
  portal root, the sessions record page and the directory record pages. Each
  would have served a raw `{{org}}` to a user. They render explicitly now; it
  is the shape of bug this mechanism invites and the reason the guard test
  checks *served* output rather than files on disk.
- **The value is escaped for its context** (HTML / JS string / plain text). It
  is settable from `/setup` and it lands on the public intake forms, so it is
  treated as untrusted input, not as our own markup.
- **`ops_mailbox_name` defaults to the organisation name** via
  `Settings.sender_display_name` — a chapter says who it is once.
- **`/healthz` reports `organization`**, which is what the fleet console
  (phase 5) will label an instance by.
- **`CHAPTER_TOKENS_URL`** — the `tokens.css` override slot: a stylesheet
  loaded immediately after the base tokens, injected by the same rewrite so no
  page needs a placeholder and the nineteenth page cannot forget one. The
  cascade is the safety mechanism. Empty injects nothing.
- **`tests/test_shared_branding.py`**, 24 cases, is the thing that keeps this
  done: it fails when a new page hardcodes the name, when a new page omits it,
  when a token survives to the browser, and when someone starts renaming
  `--cbm-*` or `cbm-` classes.

**Deliberately not built, and why.**

- **`legal-links.js`.** Making the four policy URLs settings is squarely in
  Phase 0's scope and the mechanism now exists for it, but *where the links
  should point* is a decision: three of the four currently point at the
  WPEngine staging host rather than the production site, which is a live
  Cleveland defect. Bundling a decision into a mechanical sweep is how the
  wrong URL ends up on a consent checkbox. Doug's call — see § 4.
- **The logo slot** — § 6. A feature, not a parameterization, and **ruled out
  entirely on 2026-08-26** rather than deferred.
- **The hardcoded timezone** — § 2. Phase 3.

## 8. Explicitly left alone, and why

- **`mentorprofile/frontend/`** (index.html, styles.css) — a verbatim copy of
  Cleveland's Elementor page, including 5 `clevelandbusinessmentors.org` links.
  Ruling 8 and Phase 4 retire it; parameterizing a byte-copy would fight the
  thing that makes it correct.
- **`wp-plugin/cbm-events/assets/cbm-events.css`** and
  `events/frontend/preview.css` — same reason, and the stylesheet is the class
  contract with the live site.
- **`tests/`** — assertions follow the code; they change with the sweep, not
  before it.
- **Markdown** (`prds/`, `prompts/`, guides) — these describe Cleveland as
  historical fact and are not shipped to users.
- **Comments** recording that a value came from Cleveland — provenance, not
  identity.


---

## What is still open

| Item | Kind | Where it is tracked |
|---|---|---|
| Live verification: no-flicker in a real browser, the two authenticated direct-read pages, the two `<meta cbm-org>` readers, the `/setup` round trip | verification | `OPEN-ITEMS.md` § *Live verification owed* |
| ~~The logo slot~~ | **Ruled out 2026-08-26** — no logo, no favicon. Closed, not deferred | [DECISIONS.md](DECISIONS.md) § *Decisions taken* |
| Hardcoded `America/New_York` in four files | deferred by design | [Phase 3](phase-3-spec-secrets.md) |
| The prod CRM's *Outbound Emails From Name* reading "Cleveland Business Mentoring" | CRM-side, Doug's | `OPEN-ITEMS.md` |

The logo question is ruled, so **Phase 0 now closes on the verification list
alone** — a browser pass nobody has done, set out step by step in
[TASKS.md](TASKS.md) § V1. Nothing in it blocks another phase.
