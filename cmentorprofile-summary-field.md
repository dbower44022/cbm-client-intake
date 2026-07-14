# `CMentorProfile.mentorSummary` — CRM build specification

**Status: NOT BUILT — wanted for the My Mentor Profile tool (`/mentorprofile`)
and the website mentor-page feed.** The app side shipped feature-gated: the
editor field and the preview's summary block activate on their own once this
field exists (metadata feature-detection, the `sessionTranscription` /
`googleCalendarEventId` precedent), so this build can land before or after any
app deploy. Build on **crm-test first**; prod follows. Track as a crmbuilder
program in `ClevelandBusinessMentors/programs/` per that repo's
requirement-first process.

## What this is

The public website mentor page (e.g.
clevelandbusinessmentors.org/mentor/mike-lawson/) shows a **short summary
paragraph** in its left column, under the gold "ABOUT {FIRST NAME}" label and
above the Request-a-Mentor / LinkedIn buttons — one or two sentences
positioning the mentor ("Marketing and communications executive helping
entrepreneurs …"). It is distinct from the long **About** box on the right
(which maps to the existing `aboutMentor`). Doug's ruling (2026-07-14): the
summary gets its **own dedicated CRM field** so mentors edit it directly and
the website feed reads it verbatim.

## The build (one field)

Standing in **Entity Manager → CMentorProfile → Fields → Add Field**:

| Setting | Value |
|---|---|
| Type | **Text** |
| Name | `mentorSummary` |
| Label | Mentor Summary |
| Required | No |
| Default | (none) |
| Audited | No |

Notes:
- **Text** (multi-line plain text), not Wysiwyg — the website renders it as a
  single plain paragraph; rich markup would have to be stripped by the feed.
- Layout placement is optional (staff may want it on the CRM detail layout
  next to About Mentor); the `/mentorprofile` tool edits it via the API.
- **Field-level access:** the Mentor Team role needs read+edit on it (same as
  the other mentor-editable fields), since mentors edit their own profile
  through `/mentorprofile` under their own login.

## Website-feed mapping (for the WP template)

The mentor page's dynamic slots ← CRM fields:

| Page slot | CRM source |
|---|---|
| Hero photo (gold circle) | `CMentorProfile.profilePhoto` |
| Hero name | Contact `firstName` + `lastName` |
| Hero title line (gold, under the name) | `CMentorProfile.mentorTitle` |
| Left "ABOUT {FIRST}" summary paragraph | **`CMentorProfile.mentorSummary` (this field)** |
| View LinkedIn Profile button | Contact `cLinkedInProfile` |
| Industry Experience box (semicolon-joined) | `CMentorProfile.industryExperience` |
| Areas of Expertise list | `CMentorProfile.areaOfExpertise` (labels; the page script tolerates values with no `: description` part) |
| About box (right) | `CMentorProfile.aboutMentor` |
| Page published at all | `CMentorProfile.publicProfile` |

## Verification

1. Build the field on crm-test.
2. Open `/mentorprofile` as a mentor — the "Short summary (shown on the
   website)" box appears in the Public profile group (no app deploy needed).
3. Type a summary, Save, GET-verify `mentorSummary` stored on the profile.
