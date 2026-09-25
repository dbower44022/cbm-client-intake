# Chapter-neutral wording — every place a user still reads "CBM" or "Cleveland"

**Version:** 0.2
**Status:** Sections A–E built as v0.232.0; section F and the list values open (TASKS G1 item 26)
**Owner:** Doug Bower
**Last Updated:** 09-25-26 11:00

---

## What this is

The complete list of places where a person using the software, or the CRM, still
reads the words **CBM** or **Cleveland**, measured on 09-25-26 10:47 against the tree
at commit `6f7b3cb` and against Boston's CRM configuration. Phase 0 removed the
organisation's *full name* from every page (`{{org}}`); its *abbreviation* was
left, by ruling, for a normal release (`TASKS.md` G1 item 15). This inventory is
the input to that release: what to change, what to leave, and the three
decisions the change needs.

**How it was measured.** A search of every `.html`, `.js`, `.css` and `.py`
file the application serves or runs, for the word CBM standing alone and for
Cleveland or the two Cleveland domains. Excluded on purpose, and not listed:

- **Identifiers.** `CBM.formatPhone`, `CBMBusy`, `cbm-button`, `--cbm-*`,
  `data-cbm-*`, `cbmEmail`, `cBMValueProvided`. Never shown to a user, never
  renamed (Phase 0 § 0).
- **Comments and docstrings.** Provenance, not identity.
- **Tests, documentation, plans, prompts and operator scripts.** Not user
  interfaces. The operator scripts under `scripts/` carry 19 further mentions.
- **The website stylesheet** `wp-plugin/cbm-events/cbm-events.css` and the
  mentor-profile preview stylesheet: byte copies of the website, the class
  contract (Phase 0 § 8).

## The count

| Where | Places | Mechanism |
|---|---|---|
| A. Public forms and public pages | 6, plus 8 list values that are CRM data | `{{abbr}}` token; the list values are a CRM decision |
| B. Staff and mentor tools — page text, titles and script messages | about 55 | `{{abbr}}` token (the branding rewrite already covers `.html` and `.js`) |
| C. Server messages shown to users | about 55 | a Python helper reading the same setting |
| D. Emails and calendar entries the software sends | 8 | the same helper |
| E. The settings page | 5 labels or defaults | the same helper; one default is a chapter value |
| F. The CRM's own screens | 22 distinct labels and values, in the standard's files | a CRM-standard change, ruling 4 |
| G. Cleveland and its domains | 1 message, 1 page, 3 placeholders, 3 sample lines | mostly settings that already exist |

One setting, **`ORGANIZATION_ABBREVIATION`**, default `CBM`, serves A to E, as
G1 item 15 proposed. Cleveland renders exactly as before; Boston reads BBM,
which its chapter information form already collects (`chapter.abbreviation`).

---

## A. Public forms and public pages

What an applicant or a website visitor reads.

| File and line | Text | Treatment |
|---|---|---|
| `forms/client_intake/frontend/index.html:70` | How did you hear about CBM? | token |
| `forms/client_intake/frontend/index.html:159` | I consent to receive marketing communication from CBM. | token |
| `forms/sponsor/frontend/index.html:76` | Tell us about your interest in sponsoring CBM | token |
| `forms/client_intake/frontend/app.js:377` and `frontend/shared/wizard.js:170` | Please try again or contact CBM. | token |
| `core/config.py:553` (`EVENTS_HERO_BAND` default) | CBM Workshops Program \| Business Questions, Answered Free, Live, Straightforward | **Live on Boston's public page today.** A chapter value: the form should ask for it, or the default should read from the abbreviation |
| `core/app.py:587` | FastAPI title "CBM Intake Forms" (the API documentation page) and the dev-only form index at line 425 | token or `{{org}}` |

**List values that are CRM data**, synced from the CRM by
`scripts/sync_form_options.py` and stored on every record: "CBM Client or
Volunteer" and "CBM Email" in the how-did-you-hear lists of all five forms
(`forms/*/frontend/options.js`, `forms/info_request/frontend/app.js:9`). Changing
the words changes stored data and the CRM enum together; see decision 2.

## B. Staff and mentor tools — page text, titles and script messages

| File and line | Text | Note |
|---|---|---|
| `portal/frontend/index.html:99` | User guides for all of the CBM applications. | |
| `portal/frontend/app.js:165, 167` | CBM CRM · CBM Documentation | portal link titles |
| `directory/frontend/app.js:537`, `sessions/frontend/app.js:404, 741`, `directory/frontend/record.js:1658`, `events/frontend/preview-event.js:90`, `events/frontend/preview.html:6`, `events/frontend/preview-event.html:6` | Browser tab titles "CBM — …" and "… — CBM" | 7 places |
| `directory/frontend/app.js:358, 361` | ask CBM staff | |
| `directory/frontend/mentor.js:201` | CBM email | fact label |
| `directory/frontend/record.js:951, 953, 955, 1434` | no CBM email on your profile · your CBM email address · a CBM member | |
| `directory/frontend/record.html:73` | This person has not registered for a CBM event. | |
| `myemail/frontend/app.js:137` | Your login isn't linked to a CBM Mentor profile yet | |
| `mentoradmin/frontend/app.js:396, 989, 1283` | no CBM email on the profile · tell CBM staff · no CBM email address | |
| `mentoradmin/frontend/index.html:116` | so CBM can reach them during their provisional period | help text |
| `mentorprofile/frontend/index.html:20` | how your profile will appear on the CBM website | |
| `mentorprofile/frontend/app.js:104, 127, 204` | contact CBM staff · the CBM tools · fellow CBM members | |
| `sessions/frontend/index.html:220, 454` | attended a CBM event · What CBM promised in return for this grant | |
| `sessions/frontend/app.js:1207, 4997, 5234, 5369, 5372, 5376, 5380, 5393, 5205, 3469, 7214, 8011` | CBM Contacts · Select existing CBM contact… · Add a CBM contact · Choose a CBM contact… · Couldn't load CBM contacts · CBM contact added · CBM contact removed · Add as CBM contact · the "CBM" chip and "(CBM)" suffix | 12 places, one vocabulary: "CBM contact" means a member of the chapter |
| `sessions/frontend/app.js:2773, 2775, 2777` | no CBM email on your profile · your CBM email address | compose From line |
| `sessions/frontend/app.js:3465` | a CBM member | |
| `sessions/frontend/app.js:1856, 4691, 4740, 4982, 5047, 5124, 5193, 8231` | tell CBM staff · ask CBM staff if you need it | 8 places |
| `sessions/frontend/app.js:8120` | for all client and CBM contacts. Send calendar invitations now? | |

## C. Server messages shown to users

Returned as the text of an error or a notice, or rendered into a page.

| File and line | Text |
|---|---|
| `assignments/router.py:101, 104`, `mentoradmin/router.py:113, 116`, `mentorprofile/router.py:84, 87`, `sessions/router.py:312, 315, 329`, `directory/router.py:85, 88`, `ops/router.py:101`, `myemail/router.py:82`, `events/router.py:74` | ask CBM staff to grant it · ask CBM staff if you need it · tell CBM staff (the same permission message in eight routers) |
| `assignments/auth.py:229, 232` | contact a CBM administrator (sign-in and password reset) |
| `sessions/router.py:230` | Your login isn't linked to a CBM Mentor profile yet |
| `sessions/service.py:110, 134` | field labels "CBM email", "CBM value provided" |
| `sessions/service.py:1762, 1876, 1878, 2068` | Ask CBM staff to check … · "CBM contact" fallback name · this CBM contact has no linked login user |
| `sessions/details.py:122` | turns the `cBM` prefix of a CRM field into the words "CBM …" in a label |
| `sessions/config.py:804` | overview item "CBM value provided" |
| `mentorprofile/service.py:301, 320, 386, 405, 455` | Please contact CBM staff |
| `mentoradmin/service.py:171, 179, 286, 1263` | CBM email · How they heard about CBM · no CBM email address · no CBM email on the profile |
| `comms/service.py:98, 103` | Your login isn't linked to a CBM profile · Your profile has no CBM email address |
| `directory/comms_router.py:111–113` | Your login isn't linked to a CBM mailbox … Ask CBM staff … CBM email address |
| `docs/service.py:107, 108, 419` | Your profile has no CBM email address … ask CBM staff to set it · contact CBM staff |
| `core/espo.py:167` | the CBM member you selected (a permission hint) |
| `analytics/records.py:735, 747, 759` | meetings and email activity with CBM · engagement history with CBM · people and activity with CBM |
| `forms/info_request/orchestrator.py:66` | How they heard about CBM: … (written into the CRM record's description) |

## D. Emails and calendar entries the software sends

| File and line | Text | Reader |
|---|---|---|
| `core/monitoring.py:84, 86` | sender name "CBM Intake Alerts"; subject "[CBM Intake — env]" | the alert address |
| `comms/digest.py:145, 184` | "CBM: N unread …" subject; "manage these records in the CBM apps" | every manager, daily |
| `events/notify.py:256` | fallback subject "CBM event" | registrants |
| `events/zoom_sync.py:160` | fallback Zoom topic "CBM Workshop" | registrants, in Zoom |
| `sessions/gcal.py:275, 281, 376` | no CBM email address, so no calendar event was created · "CBM Session" fallback title · "Scheduled from CBM Client Management." in every calendar event description | mentors and clients, in their calendars |

## E. The settings page

| File and line | Text |
|---|---|
| `core/settings_registry.py:247` | label "Verify CBM mailbox exists" |
| `core/settings_registry.py:215, 478` | help "never use the CBM Zoom account" |
| `core/settings_registry.py:288` | help "CBM keeps five topic playlists" |
| `core/config.py:553` | the `EVENTS_HERO_BAND` default, listed under A |

## F. The CRM's own screens

These are in the configuration files every chapter receives in step 9.6, so
today Boston's CRM says CBM on every one of them. Under ruling 4 the standard is
one configuration for all chapters, so this is one change to the standard, not
a per-chapter setting.

| File in the standard | Labels and values |
|---|---|
| `i18n/en_US/CMentorProfile.json` | CBM Email · How Did You Hear About CBM · Internal CBM Description · Create CBM Member · list values CBM Email, CBM Client / Volunteer, CBM Client or Volunteer |
| `i18n/en_US/Contact.json` | CBM Client Profile · CBM Email · CBM Client or Volunteer |
| `i18n/en_US/CPartnerProfile.json` | CBM Value Provided · CBM Partner Manager · Recognition on CBM Site · Recognition on CBM Materials |
| `i18n/en_US/CSponsorProfile.json` | CBM Manager · Primary CBM Manager |
| `i18n/en_US/Global.json` | CBM Member · CBM Members (the entity's own name) |
| `metadata/entityDefs/*.json` | the enum **values** CBM Email, CBM Client or Volunteer, Recognition on CBM Site, Recognition on CBM Materials — stored on records, not just shown |
| the captured tab list | the url tab "CBM Documentation" (step 9.7 removes it and adds none) |

The email templates in the standard carry no organisation name (checked).

## G. Cleveland and its domains

Almost all of these are settings with Cleveland defaults, which is the designed
state (Phase 0 § 1): a chapter sets them. What is not a setting:

| File and line | Text | Treatment |
|---|---|---|
| `events/frontend/app.js:1017` | "here are not visible on clevelandbusinessmentors.org" (a staff warning) | read `ORGANIZATION_WEBSITE_URL` |
| `mentorprofile/frontend/index.html:46, 54, 69, 86, 130, 136, 143` | the preview's note, five links into clevelandbusinessmentors.org and help@cbmentors.org | ruled left alone (Phase 0 § 8): a byte copy of Cleveland's website page, retired by Phase 4. Boston has no such page, so its mentors see Cleveland's |
| `mentoradmin/frontend/index.html:91, 105, 115` | help text and placeholders "@cbmentors.org", "admin@cbmentors.org", "allmembers@cbmentors.org" | read `MENTOR_EMAIL_DOMAIN` |
| `sessions/frontend/app.js:2399–2407` | sample thread "mentor@cbmentors.org" | check whether the sample renders anywhere; if not, leave |
| `core/config.py:45–95, 292, 368, 488` | the Cleveland defaults of eleven settings | designed; a chapter sets them |

---

## Recommendation

Do A to E in one release, as G1 item 15 already proposes, in this shape:

1. Setting `ORGANIZATION_ABBREVIATION`, default `CBM`, on the settings page
   under Presentation, read from `chapter.abbreviation` by the settings
   generator.
2. Token `{{abbr}}` beside `{{org}}` in `core/branding.py`, which already
   rewrites `.html` and `.js` on the way out, and a `<meta name="cbm-abbr">`
   beside `cbm-org` for scripts.
3. A helper for Python messages, `settings.abbr`, and the sweep of C, D and E.
4. A guard test like `tests/test_shared_branding.py`, so the word cannot creep
   back into a served page.

Cost: about 120 edits, each a one-word change, and the phrase "CBM contact"
becomes "BBM contact" on Boston, which is right, since it means a member of the
chapter.

## Decisions needed

1. **"CBM staff" and "CBM administrator".** Substituting the abbreviation gives
   "BBM staff". The alternative is neutral wording with no abbreviation at all,
   "chapter staff" or "your administrator", which needs no setting. Recommend
   the abbreviation: it reads as the organisation's own voice, and it is what
   the chapter form already asks for.
2. **The CRM enum values** "CBM Client or Volunteer" and "CBM Email" (how a
   person heard of the chapter). Renaming a value changes what is stored on
   every existing record and needs a data migration on Cleveland's two CRMs;
   leaving it means Boston's forms and CRM show CBM in that one list. Recommend
   leaving the values and renaming only their **labels** in the standard, which
   EspoCRM supports (`options` stay, `translatedOptions` change) — no stored
   data moves.
3. **The CRM field labels** (section F): change the standard so "CBM Email"
   reads "Chapter Email", "CBM Member" reads "Member", and so on, across the 22
   labels, applied to Cleveland's CRMs at a Sunday slot and copied to chapters
   from then on. Recommend yes, as its own handoff document, after decision 2.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.2 | 09-25-26 11:00 | Doug ruled decision 1 (substitute the acronym) and asked for the setting, named *Chapter acronym*: built as v0.232.0 — 59 page places, 46 server messages, the label tables and the hero band, with a guard test. Decisions 2 and 3 are queued as TASKS G1 item 26. |
| 0.1 | 09-25-26 10:47 | First inventory, measured against commit 6f7b3cb and Boston's CRM configuration. Requested by Doug on 09-25-26 after Boston's build showed CBM throughout its pages. |
