# Making event registration easier for people we already know

**Status:** design agreed, nothing built. Doug's rulings recorded 2026-08-17.
Companion to `CBM_Events_PRD.md` and `CBM_Events_Implementation_Plan.md`; this
covers only the registration *experience*, not the events feature itself.

## The problem

The public sign-up asks for First Name, Last Name, Email, Phone and Zip every
single time. The CRM side of "we already know you" is finished and has been
since Phase 3 — a registration finds the Contact by email, null-fills blanks
without overwriting, never relabels an existing client, mentor or partner as a
Prospect (D-09), and keeps one registration per person per event, updating the
existing row on a repeat rather than duplicating it (EV-13).

So the gap is entirely on the visitor's side. Someone who registered last month
still types all five fields; a mentor with a CBM login types them too.

## The three cases (Doug, 2026-08-17)

1. **A returning non-member, same device.** Clicking Register should recognise
   them from the device and register them with nothing typed.
2. **A returning non-member, new device.** Failing (1), ask for the email
   *first*, look it up, and register them from what we already hold.
3. **A signed-in CBM member.** Recognised automatically; they should not be
   filling in a registration form at all.

Anyone we cannot place falls through to the existing five-field form, unchanged.

## The rule that shapes all of it

**Nothing we know about a person may be returned to the browser on a public
page.** An email box that answers with a name, phone and zip turns the webinars
page into a harvester — no login, scriptable in an afternoon, and every Contact
in the CRM is reachable by guessing addresses.

So case (2) does **not** prefill a form. The visitor types their email; if we
recognise it we register them and say *"You're registered — check your email for
your join link."* Their details appear only in that email, which goes to the
address we already had. This is also fewer steps than showing a filled form to
confirm, so the safe design is the better experience.

**Corollary, and it is easy to miss:** a page that *behaves* differently for a
known address still discloses membership, even with nothing echoed. The visible
response must be identical either way — same wording, same timing — so the page
cannot be used to test whether an address is in our list. Registration for an
unrecognised address proceeds to the form; that difference is unavoidable and is
the one thing an attacker can learn, which is why it must be
**rate-limited** (`intake_rate_limit`, currently 30, must cover the lookup route
as well as the register route).

## Mechanism: signed tokens, nothing stored

Both recognition paths reuse the HMAC pattern already in `events/tokens.py`
(self-service cancel links): an identifier plus a signature keyed by the app
secret. Derived, not stored — no table, no expiry sweep, and rotating
`SESSION_SECRET` invalidates every outstanding token, which is the correct
behaviour for a secret rotation. Compared in constant time.

**Two different tokens, because they are minted at different moments:**

- **The device token** is minted in the register *response* and kept in
  first-party storage on the website's own domain (the plugin proxies, so no
  third-party cookie is involved). It signs the **email address**, not a record
  id — because with `ASYNC_DELIVERY` on, the HTTP response is sent long before
  the worker creates anything, so **there is no Contact id to sign yet**. The
  address is one the visitor typed themselves, on their own device, in
  first-party storage; the signature is what stops someone crafting a token for
  an address they do not own.
- **The re-arm token** is minted server-side *after* delivery, when the Contact
  exists, and travels in the confirmation email. Clicking it sets the device
  token on whatever device opened the mail. It signs a record id, so nothing
  identifying rides in the link. This is how someone who registered on their
  phone gets one-click on their laptop.

Neither token authenticates anybody. Each proves only "the holder of this was
issued it for this address", which is exactly the level of proof a webinar
sign-up warrants — and deliberately not enough to read or change anything.

## Prerequisite: the near-duplicate hold has to be scoped per event

`_recent_duplicate_id` in `core/app.py` holds any submission matching
**form slug + email inside 24 hours** (`duplicate_hold_seconds`). Event
registration rides the shared pipeline, so **a person registering for a second
webinar on the same day is captured as `held_duplicate` and never delivered**
until a staff member approves it in Submission Admin. They see a normal
thank-you; nothing tells them or us.

That guard exists for a real client-intake failure — a re-filled form creating a
second `CClientProfile` and, because `linkedCompany` is a hasOne, stripping the
links off the first — and event registration inherited it as collateral. Two
registrations for two different webinars are not a near-duplicate; they are the
behaviour we are trying to encourage.

**Fix:** give `FormSpec` an optional payload key that joins the match, so event
registration matches on form + email + `event_slug`. `find_recent_duplicate`
already filters on `payload["email"]` from JSONB, so a second payload key is a
small extension of the same query rather than a new mechanism. Same-event
re-submits stay held; different-event ones deliver. This lands **first** —
every path below makes returning registrants more common, which makes this bug
fire more often.

## The confirmation email (ours, not Zoom's)

**Ruling: CBM sends its own confirmation** (Doug, 2026-08-17). Today the only
mail a registrant receives is Zoom's join link, and `ZOOM_EVENTS` has never been
switched on in any environment. Three reasons it has to be ours:

- "Check your email" must be true, and for an **in-person** event there is no
  Zoom mail at all.
- The **re-arm link** and the **"not you / details wrong?"** correction link
  have to live somewhere we control.
- It is where a recognised registrant's details may safely appear.

Build it like the five follow-up kinds in `events/notify.py`: an EspoCRM
template so staff own the wording while we own the trigger, ledgered on
`followUpsSent` after a successful send so it goes once. Note `send_follow_up`
fans out across an event's whole registration list, so this needs a
**single-recipient sibling**, not a reuse of that function — the render and
ledger halves are what carry over. Zoom's join-link mail arrives alongside it
for online events; the two do not conflict.

## The member case: redirect handoff, not a shared cookie

Recognising a signed-in member on the public page is blocked by something
structural rather than difficult. The staff session cookie is
`cbm_assign_session`, **host-only** on `apps.clevelandbusinessmentors.org` with
`SameSite=lax`, and the WordPress plugin talks to us **server-side** — so the
public page never sees that cookie and neither does WordPress.

**Rejected:** setting the session cookie to `SameSite=None`. That weakens CSRF
protection across the entire staff stack — Client Administration, Mentor
Administration, Session Management, Submission Admin — to save a webinar
registrant a few keystrokes. Not a trade worth making, and it would be invisible
in review six months later.

**Agreed approach:** a redirect handoff. Register sends the member to our app,
where their existing session already identifies them; we register them in one
click and send them straight back to the event page. No cookie changes, no CORS
surface, and it works on any device they are signed in on. A visitor with no
session is bounced straight back to the normal flow, so the button never
strands anyone.

Their `CMentorProfile`/Contact is the identity; the registration is an ordinary
`CEventRegistration`, so attendance reporting (Phase 6c) treats members and
public registrants alike.

## Build order

1. Scope the near-duplicate hold per event. Small, and it is a live defect
   independent of everything else here.
2. The CBM confirmation email, with the re-arm and correction links. Everything
   else depends on it existing.
3. Email-first recognition (case 2) — the lookup route, identical responses,
   rate limiting.
4. The device token (case 1), minted on registration and re-armed from the email.
5. The member redirect handoff (case 3).

## Not yet decided

- **What "details wrong?" actually does.** A correction link implies an edit
  surface for a non-authenticated person. The narrow version — a signed link
  that lets them fix their own name/phone/zip on that one registration — is
  probably right, but it has not been specified.
- **How long a device token stays valid.** Derived tokens have no expiry by
  construction; if we want one, the signed payload has to carry a date.
- **Whether members should register from the public page at all**, or whether a
  member-facing event list inside the portal is the better home once it exists.
  The handoff above works either way.

## Verification notes

- The enumeration rule needs a test that asserts the lookup route's response is
  **byte-identical** for a known and an unknown address.
- The duplicate-hold fix needs a test proving two registrations from one email
  for **different** events both deliver, and two for the **same** event still
  hold.
- Recognition paths must be exercised as a **real non-admin visitor**, never an
  admin session — the recurring lesson from every other feature in this repo.
