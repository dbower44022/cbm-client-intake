# Birthday greetings

Plain-language reference for the birthday celebration on the portal — what it
does, who sees what, and how to test it. Built v0.177.0 (own birthday) and
v0.179.0 (the CBM-wide announcement).

**Status: LIVE on production and crm-test** (deployed 2026-07-28, both apps
verified at v0.185.0). The CRM half was driven live on crm-test — the roster
read, the own greeting, and the announcement all returned correctly. Nobody has
yet *watched* it happen on a real member's birthday; that will take care of
itself on the next one (see the data note below).

---

## What it does

When someone signs in at the portal (`/`), before their screen appears, a
fireworks display fills the window in one of two forms:

| | Who sees it | What it says |
|---|---|---|
| **Your birthday** | the person whose birthday it is | **Happy Birthday, Ada!** — "Thank you for all you do for our clients and mentors. Have a wonderful day." |
| **Announcement** | every OTHER member signing in that day | **Wish Ada Lovelace a Happy Birthday!** — "It's their birthday today — take a moment to send your best wishes." |

If it's your birthday *and* a colleague's, you get your own greeting plus a line
reading "Also celebrating today: …". If several colleagues share the day, they
are named together ("Wish A, B and C a Happy Birthday!").

The overlay closes on the **Continue** button, any click, Escape, or after nine
seconds — then the portal (or whichever app you were signing in to) loads
normally.

---

## Where the birthday comes from

The **member's own Contact record**, field **Birthday** (`cBirthday`) — the same
field members edit themselves in **My Mentor Profile → Personal details**. There
is no separate birthday field and nothing to maintain twice.

"CBM member" here means anyone with a **mentor profile** (`CMentorProfile`)
record — mentors, partner and funder managers, staff. It is not limited to the
Mentor Team.

**Only names are ever shown.** The birth date, year, and age never reach the
browser.

---

## The rules, precisely

- **The day is Cleveland's day.** Midnight to midnight in `America/New_York`,
  not the server's UTC day.
- **29 February** birthdays are greeted on **28 February** in ordinary years.
- **Greeted vs. announced are different sets, on purpose:**
  - *Greeted* (your own): **any** member who can sign in, whatever their mentor
    status. If you're in and it's your birthday, CBM wishes you well.
  - *Announced* (to everyone else): **current members only** — status Active,
    Approved, Provisional, Accepted-Provisional or Paused. Applicants (Prospect,
    Candidate, Under Review) and former members (Resigned, Retired, Terminated,
    Declined, Inactive, Dormant) are not announced as though they were still
    here.
- **Nobody is asked to wish themselves well** — your own entry is removed from
  the announcement list.
- **Once per day per browser.** The portal is re-entered on every refresh and
  every sign-in redirect; showing the overlay each time would be an irritation.
- **It never blocks a sign-in.** No member record, no linked Contact, no
  birthday recorded, or any CRM failure simply means no greeting.
- **Reduced motion is respected** — the same greeting, without animation.

---

## Seeing it for yourself

### The quickest way: the preview script (nothing is changed)

Runs the real application on your machine against crm-test, with only the app's
idea of "today" shifted — so you can see a birthday months away using real
member records, without editing anyone's Contact.

```bash
# who has a birthday on a given date? (report only)
uv run python scripts/preview_birthday.py --date 11-07 --list

# serve the portal, pretending it is that date
uv run python scripts/preview_birthday.py --date 11-07
```

Then open **<http://localhost:8010/>** and sign in with a **real CRM username
and password**:

- signed in as the person whose birthday it is → *Happy Birthday, &lt;name&gt;!*
- signed in as anyone else → *Wish &lt;name&gt; a Happy Birthday!*

`--date` takes `MM-DD` (this year) or `YYYY-MM-DD`; `--port` moves it off 8010.
The script only reads from the CRM.

> **To see it a second time**, open a private window or run
> `localStorage.clear()` in devtools — the once-per-day rule is per browser.

### The production-like way: set a real birthday

Set a member's **Birthday** to today — in **My Mentor Profile → Personal
details** for your own, or on the Contact in the CRM — then sign in at the
portal. This is the check to run after deploying.

Remember the roster is cached for up to an hour (see below), so a birthday you
have just set may take a few minutes to appear.

---

## What has to be true for it to fire

**This feature is only as good as the data.** Measured 2026-07-28:

| | member profiles | with a linked Contact | **with a birthday recorded** |
|---|---|---|---|
| **production** | 21 | 19 | **5** (all current members, so all announceable) |
| crm-test | 43 | 36 | 1 |

So in production the greeting will fire on roughly **five days a year** — real,
but rare enough that you should not read "I haven't seen it" as a fault.

Two things raise that number, both outside the app: members filling in
**My Mentor Profile → Personal details → Birthday**, or the CRM team
backfilling `Contact.cBirthday` for people whose date is already known.

A member with **no linked Contact** can't be greeted at all until that link
exists — in production that is **Sharon Rose** and **Anita Khayat** (both have
logins; Mentor Administration's completeness badge shows them as Incomplete,
and linking a Contact there fixes it). Anita's mentor status is also empty,
which would keep her out of the *announcement* even once she has a birthday
recorded — the announcement is limited to current-member statuses. Tracked in
`OPEN-ITEMS.md`.

---

## How it works (for the record)

Once per hour, the app reads the whole roster in **two** CRM calls — the member
profiles, then one batched read of their Contacts — under the org-wide API key,
and caches the result for everyone. Consequences worth knowing:

- A portal sign-in costs **no** CRM call of its own.
- The answer is the same for every viewer (it is an announcement, not
  ACL-scoped data).
- A birthday **corrected in the CRM appears within the hour**, not instantly.
- A failed read is retried after a minute, so a CRM blip heals quickly.

Code: `portal/birthday.py` (the roster and the rules),
`portal/frontend/birthday.js` (the overlay and the fireworks),
`tests/test_portal_birthday.py`. Mechanics: CHANGELOG 0.177.0 and 0.179.0.

---

## "I didn't see it" — the usual reasons

1. **Already seen today in this browser** — private window, or
   `localStorage.clear()`.
2. **No birthday recorded** for that member (the common one — see above).
3. **You are looking for an announcement about a non-current member** —
   applicants and former members are greeted but not announced.
4. **The roster is cached** — up to an hour after a birthday is added or
   corrected.
5. **The member's profile isn't linked to their login** (no Assigned User), so
   the app can't tell the birthday is *theirs* — they'd get the announcement
   about themselves instead of their own greeting. Mentor Administration's
   "Update Mentor Status" repairs those links.
6. **A deploy with no API key / dry-run** (the dev app) never celebrates.
