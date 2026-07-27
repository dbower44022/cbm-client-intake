# CRM build handoff — `Held-Duplicate` intake status

**One enum option to add, on both CRMs.** Small, but it belongs to the CRM
because the CRM is the source of truth for the intake-receipt vocabulary
(the 2026-07-27 redesign, `cintake-submission-redesign.md`).

The app already ships the behavior and **feature-detects this option**, so
nothing breaks if the build is delayed — see "Until it exists" below.

## Why

Two production incidents (2026-07-17 Christopher Maurer, 2026-07-27 Valerie
Polunas) had a client re-fill the entire intake form ~2 minutes after
submitting it — the first to name a mentor, the second to reword the request
and name a mentor. Each produced a second `CClientProfile` + `CEngagement`.

That is worse than simple redundancy: `CClientProfile.linkedCompany` is a
**hasOne** link, so creating a second profile for the same Account silently
MOVES the company and contact off the first one. In the Maurer case the
engagement staff had actually assigned to Anthony Sacco ended up pointing at a
stripped hub with no company and no contact, while the duplicate they declined
kept the good links.

The app now holds a near-duplicate for staff review instead of delivering it.
A held row needs a word in the receipt vocabulary.

## The change

**Entity Manager → `CIntakeSubmission` → Fields → `intakeStatus` (enum) →
add one option:**

```
Held-Duplicate
```

Exact spelling, capital H and D, one hyphen, no spaces — the app compares the
string literally.

Place it next to the other held values so the picklist reads in lifecycle
order:

```
Received
Completed
Held-Spam
Held-Email
Held-Duplicate     <-- new
Error
Discarded
```

Do this on **crm-test first, then production**.

Nothing else changes: no new field, no new link, no workflow, no role grant.
`intakeMessage` (which carries the explanation and the reviewer's options) and
the disposition fields already exist.

## Until it exists

`core/receipts.py:_gate_status` reads the live enum options once per process
and, if `Held-Duplicate` is not offered, writes **`Received`** on that receipt
instead. That is truthful — the submission IS in hand and undelivered — and
the full explanation still rides in `intakeMessage`:

> Possible duplicate — held for review, not yet delivered to the CRM. …

So the receipt is never rejected and no submission is ever lost. Once the
option exists, receipts start using the real word **with no deploy** (the
hourly reconciliation sweep converges the existing rows).

Submission Admin is unaffected either way — it reads the app's own status, so
held duplicates show as **Held-Duplicate** there from day one.

## Verification

After adding the option on crm-test:

1. Submit the client-intake form, then submit it again from the same email
   within 24 hours (a fresh page load, so a new submission token).
2. The second one appears in Submission Admin with Intake status
   **Held-Duplicate** and Response status **Awaiting review**.
3. Open its `CIntakeSubmission` receipt in the CRM: `intakeStatus` reads
   `Held-Duplicate` and `intakeMessage` explains the decision.
4. Confirm no second `CClientProfile` / `CEngagement` was created.
5. Press **Approve** in Submission Admin — it delivers, and the engagement is
   created against the client's EXISTING profile (not a new one).
