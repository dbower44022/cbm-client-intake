# How to update the CRMs — step by step

**The procedure for getting a configuration change onto every EspoCRM instance in
the network, in the same shape, verified.**

This is the CRM half of the release train (ruled weekly, Sunday **17:00 UTC**).
The app half — build an image, deploy it — is `DEPLOYMENT.md`. This document is
the half nobody has written down, and it is the half that has gone wrong: the two
Cleveland instances have drifted from each other repeatedly, and every one of the
traps in § 7 is something this project has actually been bitten by.

**Read § 7 before your first run.** It is short, and it is the difference between
a build that works and a build that looks like data loss.

---

## 1. Which world are you in?

The procedure has two forms, and today only one of them exists.

| | **Today (N = 2)** | **The train (N chapters)** |
|---|---|---|
| Who applies the change | A human, in Entity Manager, following a handoff document | The applier, headless, from the release train |
| How it is described | A `*-crm-handoff.md` file at the repo root | A versioned desired-state definition |
| How you know it worked | `scripts/preflight_crm.py`, run by hand | The same check, run as a deploy gate, reporting JSON to the fleet console |
| How you know which version an instance holds | You do not | `CNetworkStandard` (built by TASKS § R0) |

**Everything below is written for today**, because that is what can be executed
this Sunday. § 8 says what changes when the applier lands — and the shape of the
procedure does not change, only who performs steps 4 and 9.

**The order never changes: crm-test first, always, then production.** Not because
crm-test is less important, but because it is the only place a mistake is
recoverable without a support call.

---

## 2. Before you start

**You need an Admin-type EspoCRM account.** Schema changes are admin-only —
EspoCRM 403s the org-wide API key on `Admin/fieldManager`. Verified again on
crm-test 2026-08-24: that key gets HTTP 200 on `Team` and `EmailTemplate` and
**403 on `Role`**. There is no partial admin in EspoCRM.

- **crm-test**: use your own admin login.
- **production**: the admin credentials (`ESPO_PROVISION_USERNAME` /
  `ESPO_PROVISION_PASSWORD`) exist **only on the deployed web component**. Reach
  them by running the script inside the container from the DigitalOcean app
  console — do not copy a production admin password onto a laptop.

**You also need to know what "done" looks like before you start**, which is what
the handoff document in step 1 is for. A change applied without a written
definition of the correct end state cannot be verified, only admired.

---

## 3. The procedure

### Step 1 — Write the change down first

Create or update a `*-crm-handoff.md` at the repo root. One file per CRM change.
`cnetworkstandard-entity-crm-handoff.md` is the smallest current example;
`cgrant-entities-crm-handoff.md` is the fullest.

It must be written in **Entity Manager vocabulary** — the words on the screen the
person will actually be looking at — never in metadata vocabulary. It must state:

- what is being built and **why**, in a paragraph someone can disagree with;
- every entity, with its **Type**, stream on/off, and whether it gets a nav tab;
- every field, with name, type and any constraint;
- every link, with the two Name boxes filled in **as they appear in the dialog**
  (see § 7 — the boxes are inverted and this has been got wrong four times);
- the **role grants** the app needs, which is the step most often forgotten;
- **how to verify**, with the exact request and the exact expected response.

If the change is large or repetitive, write a script instead and let the handoff
point at it — `scripts/migrate_event_schema.py` is the worked example, and its
properties are the ones any such script must have: dry-run by default,
read-before-write, idempotent, admin-type asserted before it touches anything.

### Step 2 — Decide whether this change is additive

**Additive** — new entity, new field, new enum option, new link, widening a
length, clearing a read-only flag. These are safe to apply ahead of the code that
uses them, and they are what the weekly slot is for.

**Not additive** — removing or renaming a field or link, narrowing a type,
deleting an enum option in use. These change behaviour for code that is *already
running*, and applying one before the new image is live opens an incident for the
width of the deploy.

A non-additive change does not ride the normal slot. It gets its own window, its
own announcement, and a human watching. Say which kind it is in the handoff.

### Step 3 — Check the starting state

Run the conformance check against crm-test and record the output. You want to
know what was already wrong *before* you change anything, so that anything wrong
afterwards is yours.

```
uv run python scripts/preflight_crm.py \
  --url https://crm-test.clevelandbusinessmentors.org --key <ORG_API_KEY> --json \
  > /tmp/crm-test-before.json ; echo "exit=$?"
```

Exit **0** is conformant, **1** is drift, **3** is "could not be checked" — which
is not the same as bad, and usually means a credential or a network problem
rather than a CRM problem.

### Step 4 — Apply to crm-test

By hand in Entity Manager, following the handoff. Or, if the change has a script:

```
PYTHONPATH=. \
ADMIN_BASE=https://crm-test.clevelandbusinessmentors.org \
ADMIN_USER=<admin> ADMIN_PASS=<password> \
uv run python scripts/migrate_event_schema.py          # dry run, changes nothing
```

Read the printed plan. **Then** re-run with `--apply`. The dry run is not
ceremony: it is the only chance to notice that the plan is bigger than the change
you meant to make.

### Step 5 — Rebuild

EspoCRM caches metadata aggressively; a change that does not appear is usually a
missed rebuild rather than a failed write.

- In the UI: Administration → **Clear Cache**, then **Rebuild**.
- On the crm-test droplet (`CBM-TEST`, Dockerized):
  `docker exec -u www-data espocrm php command.php rebuild`

The scripted path already calls `Admin/rebuild` at the end.

### Step 6 — Verify the shape, not the screen

Read the metadata back and confirm the change landed where you intended. **Do not
trust the Entity Manager list view** — it shows labels, and labels hide the
prefix bugs in § 7.

```
GET /api/v1/Metadata      →  entityDefs.<Entity>
```

Confirm the entity name has exactly one `C`, each field is where you put it, and
each link is on the side you intended.

### Step 7 — Verify the grants, as the app sees them

Two different credentials, two different checks, and skipping either is how a
change ships broken.

1. **As the org-wide API key** — the credential the application actually runs on:
   ```
   GET /api/v1/<Entity>?maxSize=1     with X-Api-Key
   ```
   HTTP 200 is right, even with `total: 0`. **403 means a role grant was missed**
   and the feature will be invisible to the app.
2. **As a real non-admin user** in the relevant team, in a browser.
   **Admins bypass ACL entirely**, so an admin test proves nothing about whether
   a mentor or a staff member can actually use this. Several bugs in this project
   stayed invisible for weeks because they were only ever tested as an admin.

### Step 8 — Re-run the conformance check, and diff

```
uv run python scripts/preflight_crm.py --url <crm-test> --key <ORG_API_KEY> --json \
  > /tmp/crm-test-after.json ; echo "exit=$?"
diff /tmp/crm-test-before.json /tmp/crm-test-after.json
```

The diff should contain your change and nothing else. Anything else that moved is
either a second change you did not mean to make, or something the CRM team
altered underneath you — both worth knowing before production.

### Step 9 — Soak for the week

The change sits on crm-test until the Sunday slot. This is the point of a weekly
cadence: real use on a real instance is a better test than any checklist.

**One thing about crm-test that matters here.** It resets nightly from a fixed
snapshot — the CRM at 04:00 UTC, the app database an hour later. **Entity Manager
work survives**, because the reset rebuilds from the files your change wrote.
**Records do not.** So a schema change persists through the week; the test records
you created to exercise it are gone by morning. Do not read an empty record list
on Monday as a failed build.

### Step 10 — Apply to production, Sunday 17:00 UTC

Same change, same order, from the same handoff document. Nothing new is decided
here — if you find yourself making a judgement call on production that you did not
make on crm-test, stop, because the two instances are now diverging and that is
the thing this whole procedure exists to prevent.

Production admin credentials live only on the deployed web component, so run any
script from inside that container via the DigitalOcean app console.

Repeat steps 5, 6 and 7 against production.

### Step 11 — Record what you did

1. Mark the handoff document as built, with the date and which instances.
2. Note it in `CHANGELOG.md` if the app gains behaviour, or in `OPEN-ITEMS.md` if
   something is still owed.
3. Once TASKS § R0 has built `CNetworkStandard`, the applier stamps the version
   automatically — **and only after a complete successful apply**. A partial apply
   must leave the previous stamp untouched: an instance claiming conformance it
   does not have is worse than one claiming nothing, because the fleet console
   believes it.

### Step 12 — Confirm Monday morning

**The Sunday slot means nobody is watching when it lands.** Until the fleet
console exists, a human looks on Monday: `/healthz` on each app, the conformance
check exit code on each CRM, and one real non-admin user opening one gated page.

Five minutes. It is the compensating control for an unattended cut.

---

## 4. If it goes wrong

**A field or entity did not appear.** Almost always a missed rebuild (step 5) or
the name picked up an extra `C` (§ 7). Check `GET /Metadata` before assuming the
write failed.

**A write returned 200 but the value did not store.** Field-level ACL silently
strips writes. The tell is newer fields saving while older ones do not. Diagnose
by reading each role's `fieldData` as an admin.

**A list request returned nothing.** If the page size was over 200, EspoCRM
**refused** it with a 403 rather than truncating — and inside a best-effort
handler that reads as "no records". Page at 200 or below.

**You need to undo an additive change.** Deleting a field or link in Entity
Manager is **metadata-only** — the column and its data stay. A same-named recreate
re-adopts the data; a **mis-named** recreate strands it in the old column and
leaves an empty new one, which reads exactly like data loss and is not.

**Production is broken and crm-test is fine.** Compare them directly rather than
reasoning about it: run the conformance check against both and diff the JSON.
That comparison is the single most useful thing in this document.

---

## 5. What must never ride the automatic slot

When the applier runs unattended, the automatic path **may create and widen, and
nothing else**. Removals, narrowings and type changes are a separate, deliberately
triggered job with a human in front of it.

The reason is timing, not caution: a pre-deploy job changes the CRM **before the
new app code is live**, so anything that removes or narrows something the
currently-running code still uses opens a live incident for the width of the
deploy.

---

## 6. Roles and teams — the part that is not schema

Teams and role grants are as much a part of "the configuration" as fields are, and
they are where the two Cleveland instances actually differ.

- **Teams** are named in `core/config.py` — seven of them, and every team gate in
  the product resolves one of those strings. A missing team is a locked-out app.
  All seven exist on both instances (verified 2026-08-24).
- **Roles** are named nowhere in this repo, deliberately, and exist only inside
  the live CRMs. They are known to differ between crm-test and production. Until
  TASKS § R4 captures and adjudicates them, **a role change is a hand edit on each
  instance and there is no detector for it** — so write it in the handoff and do
  it in the same session on both, or it will drift.

---

## 7. The traps

Every one of these has already cost this project time.

| Trap | What happens | What to do |
|---|---|---|
| **Entity names get a `C` prepended, always** | Typing `CGrant` builds `CCGrant` | Type the name **without** the `C` |
| **Field names are prefixed only on non-custom scope** | A field on `Contact` typed `ratings` becomes `cRatings`; on a custom entity it stays as typed | Type unprefixed on system entities; exactly as written on custom ones |
| **The Create Link dialog's two Name boxes are inverted** | The link lands on the wrong side. Got wrong **four times** | Work out both link names first, write each under the panel of the entity it **points at**, then verify in `GET /Metadata` |
| **Deleting a link is metadata-only** | The column and its data survive; a mis-named recreate strands them | Recreate under the **same** name; never rename around a mistake |
| **`maxSize` over 200 is a 403, not a truncation** | Inside a best-effort handler it reads as an empty list — this emptied every link picker in production | Page at 200 or below |
| **Field-level ACL silently strips writes** | HTTP 200, and the field did not store | Read each role's `fieldData` as admin |
| **Admins bypass ACL entirely** | Everything works for you and nothing works for staff | Test as a **real non-admin** in the relevant team |
| **The Entity Manager "Read-only" checkbox is a UI parameter** | It never blocks an API write | Fine for app-maintained fields; useless as a security control |
| **Currency fields validate against their `*Currency` companion** | The save 400s | Always set the companion |
| **Soft deletes** | An admin GET returns a deleted row with `deleted: true`; ordinary users get 404 | Treat `deleted: true` as gone |
| **Some system entities are not customizable** | The field build is impossible, e.g. `EmailTemplate` | Check `scopes.{Entity}.customizable` **before** speccing |
| **The CRM team edits crm-test underneath the app** | Something that worked stops | Check field and enum drift first |
| **A role names a scope the target does not have** | EspoCRM 10 rejects the whole role (HTTP 400 *Scope X is not allowed*). crm-test's roles name Advanced Pack and Google Integration scopes | Install the extensions first, or filter the capture per target and record each strip as *unapplyable* |
| **A role's field-level entry names a deleted field** | Same rejection (*Field X does not exist in Y*); the source tolerates the stale entry, the target does not | Validate `fieldData` against `entityDefs` before writing; clean the source |
| **The file half is TWO trees** | Copying `custom/Espo/Custom/` alone leaves the CRM's own UI blank — `clientDefs/App.json` names a view that lives in `client/custom/src/` | Copy both, `chown www-data`, rebuild; sign in to the CRM and look, not just the app |

---

## 8. What changes when the applier exists

The shape of this procedure does not change. Two steps change hands.

- **Step 4 and step 10 stop being human work.** The applier reads the desired
  state and reconciles each instance to it: dry-run, review the plan, apply *that
  exact plan*, refusing if the plan has moved since it was reviewed.
- **Step 3 and step 8 become automatic.** The conformance check runs as a
  PRE_DEPLOY gate and fails the deploy on drift, so an instance whose CRM does
  not hold what the code expects cannot receive that code.
- **Step 11's stamp is written by the applier**, and step 12's Monday check
  becomes the fleet console showing "18 conformant, 1 drifted, 1 unreachable"
  rather than a person opening tabs.
- **Steps 1, 2, 5, 6 and 7 remain human**, and always will: deciding what the
  change is, whether it is additive, and confirming a real non-admin can use it.

Everything else in this document survives that transition, which is why it is
worth writing now rather than after.
