# Last Client Assigned Date — CRM field handoff (`CMentorProfile`)

Doug's request (2026-08-22): **track the last date a mentor was assigned a new
client**, and have the Client Administration app set it when it assigns one.

Status: **the app half is built and shipped; the CRM field is not built yet.**
The stamp is feature-detected, so the app is inert until the field exists and
starts writing it the moment it does — no deploy, no coordination window.

## The field to build

Entity Manager → **CMentorProfile** → Fields → Add Field.

| Setting | Value |
|---|---|
| Type | **Date-Time** |
| Name | **`lastClientAssignedDate`** — type it exactly; the app looks for this name |
| Label | **Last Client Assigned** |
| Read-only | **Yes** (see below) |
| Default | *(none)* |
| Required | No |
| Audited | Recommended — this is the kind of value staff will want a history for |

Notes on the choices:

- **Date-Time, not Date**, to match `CEngagement.engagementAssignedDate`: the two
  are written in the same action, from the same clock, and the app compares them
  directly. EspoCRM stores datetimes as UTC and renders them in the viewer's
  timezone.
- **`CMentorProfile` is a custom entity**, so the name takes no `c` prefix — the
  field sits alongside `acceptingNewClients`, `mentorStatus` and `cbmEmail`.
  (The blind-`c`-prefix rule only bites on non-custom entities like Account and
  Contact.)
- **Read-only** because the app maintains it. Staff who need to correct a value
  can clear the read-only flag temporarily, or an admin can edit it directly.
  Nothing in the app reads the field back except its own advance-only guard, so
  a hand-edit is safe.

**Both CRMs.** Build it on **crm-test** and **production** — the app writes to
whichever CRM it is pointed at, and detects the field per environment, so
building it on one gives you the behaviour on that one only.

### Put it on a layout (optional — for CRM users)

Client Administration already shows the value (see below), so these placements
are for people working in EspoCRM directly. All Entity Manager →
CMentorProfile → Layouts:

- **List** — a "Last Client Assigned" column on the mentor roster.
- **Detail** — on whichever panel carries `acceptingNewClients` and
  `maximumClientCapacity`; that panel is already about capacity.
- **Search filters** — makes "not assigned since <date>" a saved filter.

## Where the app shows it

**Client Administration → Review Mentors** (the *Available Mentors* picker) has
a sortable **Last Assigned** column, between Assigned (30d) and Lifetime.

- Sorted **ascending** it answers the question the field exists for: who has
  gone longest without a client. Never-assigned mentors render **"—"** and sort
  to the top of that order.
- Until the CRM field is built, every row reads "—" — the column is live, the
  data is not. The count columns beside it are what say whether a mentor has
  clients at all.
- The roster query asks for the field only when the CRM has it
  (`_mentor_select`), for the same reason the write is detected: an unknown
  attribute in `select` is not something to bet a staff grid on.

The same rows feed the **/mentoradmin** roster, which carries the value in its
payload but does not display it — that grid can gain the column later with no
server change.

## What the app does with it

`assignments/service.py` — `stamp_mentor_last_assigned()`, called from the two
actions in Client Administration that hand a mentor a client:

| Action | Stamps? | Which mentor |
|---|---|---|
| **Assign** (`POST /engagements/{id}/assign`) | yes | the mentor being assigned |
| **Reassign Mentor** (`POST /engagements/{id}/reassign`) | yes | the **new** mentor only — the outgoing one is untouched, because the field records gaining a client, not losing one |
| **Repair assignment…** (Assign with the same mentor) | **no** | a repair re-runs the re-homing for an assignment that already happened; it is not a new client, which is why the engagement's own `engagementAssignedDate` is left alone too |

Three properties worth knowing:

- **Feature-detected per write.** The app reads
  `entityDefs.CMentorProfile.fields` and skips the stamp when the field is
  absent. A metadata failure is treated as "unknown", not "absent", and is never
  cached — a CRM hiccup does not turn the feature off for ten minutes.
- **Advance-only** (the `touch_last_contact` rule): a stored value at or after
  the new one is left alone, so the date can never move backward.
- **Best-effort.** The write runs as the signed-in staffer, so their EspoCRM ACL
  applies. If their role has no **edit on CMentorProfile**, the stamp is refused
  and *logged as a warning* — the assignment itself, already written, still
  stands. The response carries `mentorLastAssignedDate: null` and the action-log
  entry records it.

### The one ACL thing to check

The **Client Administration Team** role needs **edit** on `CMentorProfile` for
the stamp to land. It already needs **read** (the mentor dropdown), so this may
already be granted — confirm on both CRMs via Administration → Roles, or watch
for `lastClientAssignedDate not stamped on CMentorProfile/...` in the app logs
after the first assignment. Admin accounts bypass ACL entirely, so **testing
this as an admin proves nothing** — sign in as a real Client Administration
staffer.

## Verifying it

1. Build the field on crm-test.
2. In Client Administration, assign a Submitted engagement to a mentor.
3. **Review Mentors → Last Assigned** shows today's date on that mentor's row
   (and the same value is on the mentor's record in EspoCRM). Click the column
   header twice to sort ascending — the mentors who have waited longest, and any
   still showing "—", come to the top.
4. Reassign the same engagement to a second mentor: the second mentor is
   stamped, the first mentor's value is unchanged.
5. Right-click the assigned row → **Repair assignment…**: no new stamp.

## A note on the alternative that was not taken

The same question can be answered without a new field: the app already sweeps
every `CEngagement` for its per-mentor metrics (`mentor_engagement_metrics` —
Active Clients, Assigned last 30 days, Lifetime), and the **maximum**
`engagementAssignedDate` per mentor is exactly this date, derived, with full
history and no CRM build.

A stored field was chosen anyway because a derived value lives only inside this
app: it cannot be a roster column, a search filter, a report field or a workflow
trigger in EspoCRM. If the value is ever suspected of being wrong (an assignment
made directly in the CRM, which the app never sees), the derived number is the
one to reconcile against.
