# Running a training session on the sandbox

For whoever is delivering the training. It covers who to sign in as, what to
click, what to tell the room, and what the overnight reset does.

Two documents, and the split matters so they don't drift:

- **This page** — what to *do*: the walkthroughs, the ground rules, the reset.
- **`demo-records.md`** — what's *on* each record: the tab-by-tab inventory,
  the contribution amounts, the coverage figures.

Engineers setting the sandbox up want `SANDBOX-RESET.md` instead.

> **Status.** The sandbox data is live and ready. The overnight reset is
> **built and tested but not yet switched on** — until it is, the sandbox keeps
> whatever state a session leaves it in. Check with whoever runs the platform
> before assuming last night's changes are gone.

## Before you start — five minutes

1. Open **`cbm-client-intake-svxs3.ondigitalocean.app`** and sign in as
   `joe.mentor@cbmentors.org`.
2. Look at the **footer**. It must read **`(Test)`** after the version number.
   If it says `(Production)` you are in the wrong system — stop.
3. Open **Client Management**. You should see **seven clients**. If the list is
   empty or short, something has gone wrong; don't improvise, ask.

That's the whole check. If those three things look right, everything below
will work.

## What to tell the room

Three things, at the start:

- **This is a training system.** Every business, person and email address in it
  is invented. Nothing here is a real CBM client.
- **You are not expected to save anything** — we're looking, not editing.
- **But if you do save something, it's fine.** Nothing can escape: no email is
  sent, no calendar invitation goes out, and no document reaches CBM's real
  Drive. Every address ends `@sandbox.cbmentors.org`, which is a dead end on
  purpose.

That last point is worth saying out loud. People hesitate to click things in a
demo, and the hesitation costs more than the mistake would.

## Sign-ins

One login per audience. Ask an administrator for the passwords; they're set in
the CRM and are the same ones each time.

| Audience | Sign in as |
|---|---|
| Mentors | `joe.mentor@cbmentors.org` |
| Client Administration | `kitty.cat@cbmentors.org` |
| Mentor Administration | `mentoradmin@cbmentors.org` |
| Partner Management | `partner.manager@cbmentors.org` |
| Funder Management | `sally.sponsor@cbmentors.org` |
| Submission Admin | `mark.marketing@cbmentors.org` |

**Nobody trains on their own login.** Signing in as yourself puts your real
mailbox behind the Send button — the containment above only holds for these
accounts.

---

## Walkthrough — mentors

Sign in as **Joe Mentor**. This is the main one; allow 30–40 minutes.

**1. The client list.** Seven clients, statuses down the side — Active,
Assigned, On-Hold, Completed. Show the status filter and the search box before
opening anything, so people see the shape of their own future list.

**2. Open `Brightline Bakehouse — Mentoring`.** This is the record everything
else hangs off. Land on **Overview** and point out the facts rail, the notes,
and the **Next session** callout with a real date on it.

**3. Sessions tab.** Eight of them — seven held over the past year, one
scheduled ahead. Open a completed one and show the notes and next steps. This
is the screen mentors will spend the most time in, so don't rush it.

**4. Communications tab.** A five-message thread about financing a second
oven, alternating between Joe and the client. Show that the history lives on
the record rather than in someone's inbox — that's the point of the feature.

**5. Contacts tab.** Dana Whitcomb, with a phone number, an address, and the
agreements badge showing all three consents accepted.

**6. Details tab.** Every field is filled in, so this is a fair picture of what
a complete client record looks like.

**7. My Mentor Profile.** Joe's own record: bio, expertise, availability,
photo. The live preview on the right is exactly what the public website shows,
which usually lands well.

Optional, if the group is engaged: `Marlow Pet Supply — Mentoring` is a
**Completed** engagement with eleven sessions — useful for showing what a
finished relationship looks like.

## Walkthrough — Client Administration

Sign in as **Kitty Cat**, open **Client Administration**.

**1.** Four engagements sit at **Submitted** — Ember Lane Florists, Kestrel
Fabrication, Pinehurst Tutoring, Quarry Street Coffee. These are the ones
waiting for a mentor.

**2. Assign one.** Pick Ember Lane Florists. The mentor dropdown offers nine
eligible mentors; explain that a mentor only appears if they're Active,
accepting new clients, and have a login.

**3.** After assigning, the email compose opens pre-filled with the mentor's
address and the assignment template. **Don't send it** — but do show it, and
say the send is what tells the mentor they have a new client.

**4. The Notes column** is staff-internal and edits in place. Five rows already
have notes; `Whitmore Automotive` reads *"Unresponsive since spring. Consider
closing."*

**5. Right-click any row** for the full menu — Reassign, Repair assignment,
Notes. Use `Halstead Print Works` for Reassign; it's assigned with a single
session, so the before-and-after is easy to see.

## Walkthrough — Mentor Administration

Sign in as **Mentor Admin**, open **Mentor Administration**. Twenty-six
mentors.

**1. Open `Joe Mentor`.** Reads **Complete** — a linked contact, all three
sign-offs, a CBM email, and a login attached to both the profile and the
contact. This is what a properly set-up mentor looks like.

**2. Open `Claudia Reinhart`.** Reads **Incomplete**, and names why: training
and terms not confirmed. She's a Candidate, so that's the correct state — the
badge is telling you where she is in onboarding, not that something is broken.

**3.** Nine mentors are Incomplete for a different reason — Active but with no
login. That's the backlog the **Update Mentor Status** sweep exists to surface.
Worth running the sweep so people see it report rather than guess.

**4.** The status filter spans Active, Approved, Provisional, Candidate, Paused
and Inactive.

## Walkthrough — Partner Management

Sign in as **Partner Manager**, open **`Cuyahoga Small Business Alliance`**.

Overview, then **Sessions** (four quarterly meetings), **Communications** (a
four-message thread about the spring referral cohort), and **Referred
Clients** — two engagements credited to this partner, which is the tab that
usually prompts questions about attribution.

The **Discussion** pane on Overview is worth explaining even though it's empty:
it's internal, append-only, and never visible to the partner.

## Walkthrough — Funder Management

Sign in as **Sally Sponsor**, open **`Harrowgate Family Trust`**.

The **Contributions** tab is the reason this is the funder demo: five gifts
totalling $63,700, spanning Received, Committed and Pledged, across Grant,
Sponsorship and Donation including one In-Kind. Every state anyone will ask
about is on one screen.

Then Sessions (four) and Communications (a three-message thread about renewing
the 2027 grant).

## Walkthrough — Submission Admin

Sign in as **Mark Marketing**, open **Submission Admin**.

**The queue is currently empty**, so this one demonstrates the screen rather
than the workflow. Explain the two status axes — what happened to the arrival
versus where the reply conversation stands — and leave it there. If you need a
populated queue for a session, ask ahead of time; it can be seeded.

---

## How the overnight reset works

**In one sentence:** every night the sandbox goes back to exactly the state
described in `demo-records.md`, so every session starts from the same screens.

**What happens.** At midnight the CRM is restored from a saved snapshot. An
hour later the app's own working data — the Submission Admin queue, record
comments, the document index — is cleared to match. The two run an hour apart
so they can't overlap.

**What comes back.** Everything: every client, mentor, session, email thread,
contribution and event, exactly as it is today. Anything created during a
session disappears. Anything edited returns to its original wording. Anything
deleted comes back.

**What survives on purpose.**

- **The logins and their passwords.** They're part of the snapshot, so they
  work the next morning unchanged. If a trainee changes their own password
  during a session, it reverts to the original — which is usually what you
  want.
- **Anything the CRM team changes in the CRM's own setup** — new fields,
  layouts, roles. The reset clears the *data*, not the system's design.

**What to expect the morning after.** Everyone is signed out — the reset clears
active sessions — so the first sign-in of the day is a fresh one. That's
normal, not a fault.

**What the reset cannot undo.** Nothing, in practice, because nothing escapes:
no email leaves the system, no calendar invitation is created, and documents go
to a separate sandbox Drive rather than CBM's real one. This is why "if you do
save something, it's fine" is a safe thing to tell the room.

**Pausing it.** If you need the sandbox to keep its state overnight — a session
running late, or something you want to look at again tomorrow — ask whoever
runs the platform to pause that night's reset. It's a one-line change and it's
designed to be used.

## When the demo data needs changing

**Don't fix it by hand.** A record you correct in the CRM will look right this
afternoon and be gone by tomorrow morning, because the snapshot doesn't know
about it. That's the single most confusing thing about this environment, and
it catches people out.

Instead, say what you need and it gets added to the scripts that build the
sandbox, then a new snapshot is taken. Same effort, and it survives.

Reasonable things to ask for: a populated Submission Admin queue, a second
co-mentored client, documents on a record once that's possible, more clients if
the grids feel thin.

## If something looks wrong

Check the footer says `(Test)` and that Joe Mentor still has seven clients. If
either is off, stop and ask rather than working around it — a restore takes
about half a minute and is the normal fix, not a drama.
