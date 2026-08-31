# CNetworkStandard — CRM build handoff

Written in **Entity Manager vocabulary** — "LEFT" means the entity whose
Relationships tab you are on, though this build has **no relationships at all**.
Plan: `prds/chapter-network/phase-1-crm-config.md`; the ruling that chose this
shape over the two alternatives is `prds/chapter-network/TASKS.md` § D1
(Doug, 2026-08-26). Nothing here exists yet.

**Build on crm-test first**, verify, then production.

> **Built on crm-test 2026-08-27.** Structurally correct first time. Two things
> were missed and are now fixed, both worth reading before the production run:
> the § 4 **role grant** was not applied, so the org-wide API key got HTTP 403 —
> the entity existed and was invisible to the application, which is the one
> failure mode that makes this whole design pointless; and the entity was left in
> the **navigation tab list** contrary to § 1. Verified afterwards by the
> effective ACL the app itself sees — `{create: no, delete: no, edit: no,
> read: all}` — and `GET /api/v1/CNetworkStandard` as the org key returning
> **HTTP 200, `total: 0`**. **Production: built 2026-08-31** by Doug running
> `scripts/build_networkstandard.py` from inside the deployed web container —
> dry run, then `--apply --expect 54fb5b37192027f7 --production`. All eight
> steps `DONE` (the create added the entity to the tab list; the script removed
> it, 39 → 38). Read back as the org key: five plan fields, zero custom links,
> no `CCNetworkStandard`, `GET /api/v1/CNetworkStandard` → HTTP 200 `total 0`.
>
> **Build it from the script, not by hand:** `scripts/build_networkstandard.py`
> covers the ENTIRE handoff — the entity and fields (read from
> `scripts/plans/cnetworkstandard.json`, the plan crm-test was built from), the
> § 4 role grant, the § 1 tab rule, and the § 5 verification as the org API key.
> It is self-contained (the general applier lives in the gitignored `.claude/`
> skill and never reaches the deployed image, where production's admin
> credential lives), idempotent, and dry-run by default; `--apply` demands the
> dry run's `--expect` fingerprint, and a non-crm-test target additionally
> demands `--production`. Rehearsed 2026-08-30 inside the crm-test web
> container against the finished instance: every step `ok`, org-key GET 200
> `total 0`, exit 0.

This is the smallest handoff in the repo: **one entity, five fields, no links, no
enums, no formulas.** That is deliberate and it is the point — read § 0.

---

## 0. What is being built and why

Every chapter in the network runs its own EspoCRM, and they must all hold the
same configuration. Phase 1 builds the machinery that applies a versioned
configuration standard to an instance. This entity is where that machinery
**records what it applied**, so the question "is this chapter's CRM up to date?"
can be answered by reading one row instead of sweeping every field.

Think of it as the CRM's equivalent of the Alembic version table in the app's
Postgres.

**Why an entity rather than a setting or a log row.** Three properties decided it:

1. **It describes the CRM, so it must survive the app.** A chapter's app can be
   redeployed, reconfigured or replaced entirely; the stamp has to still be there
   afterwards. That rules out storing it in an app environment variable.
2. **Only the applier may write it.** An environment variable could be edited by
   anyone with the DigitalOcean console, and would then *lie* — which is worse
   than having no stamp at all, because the fleet console would believe it.
3. **The app must be able to READ it with the ordinary org-wide API key.** This is
   the one that settled it. Probed on crm-test 2026-08-24, read-only: the API key
   gets HTTP 200 on `Team` and `EmailTemplate` and **HTTP 403 on `Role`.** So
   EspoCRM's admin-only surfaces are genuinely closed to the credential the
   application runs on — storing the stamp under admin Settings would have meant
   putting admin credentials into application runtime, which the interface
   contract (`prds/chapter-network/interface-contract.md`, C2) exists to prevent.

**One row, forever.** EspoCRM has no "single record entity" type, so this is a
convention the applier maintains rather than something the schema enforces: there
is exactly one `CNetworkStandard` record per instance and the applier **updates it
in place**. If two ever appear, that is a defect in the applier, not a data model
question — the fleet console should treat it the same as a missing stamp
(conformance unknown), because "which row is current" has no answer.

**Nothing writes to this until the applier exists.** Building it now is
deliberate: an instance that holds the entity and no row reads as *"configured to
report, has never been applied to"*, which is the honest state of every instance
today, and it lets the app's `/healthz` `crmConfig` block ship against a real
scope instead of a hypothetical one.

---

## 1. `CNetworkStandard`

Administration → Entity Manager → **Create Entity**.

- **Name:** `NetworkStandard` — **type it WITHOUT the C.** EspoCRM's
  `NameUtil::addCustomPrefix()` prepends it unconditionally
  (`customPrefixDisabled` is `false` on this instance), so `NetworkStandard`
  becomes `CNetworkStandard`, and typing `CNetworkStandard` would yield
  `CCNetworkStandard`. That is exactly how the grant build produced `CCGrant`.
- **Label:** `Network Standard` · **Plural:** `Network Standards`
- **Type:** `Base` — not `BasePlus`. There is no assigned user, no teams, no
  collaborators: nobody owns this record, a machine writes it.
- **Stream:** **off.** The applier writes this on every successful apply; a stream
  would fill with machine noise nobody reads.
- **Disable the navigation tab.** It is machine state, not something staff work
  with. Administration → User Interface → Tab List: leave it out.

| Name | Type | Notes |
|---|---|---|
| `name` | varchar | **Required** by EspoCRM on every entity. The applier supplies the standard version, so the row is self-describing in any list view — e.g. `"2026.09.1"` |
| `standardVersion` | varchar | The configuration standard's version, and the field everything reads. Same value as `name`; `name` exists because EspoCRM demands it, this exists because reading business meaning out of `name` is how fields get repurposed later |
| `appliedAt` | datetime | When the apply **completed**. Not when it started — a partial apply must not stamp at all (§ 3) |
| `appliedBy` | varchar | Which account applied it, so an unexpected change is traceable to a credential |
| `planFingerprint` | varchar | The fingerprint of the dry-run plan that was applied, carried over from the applier's plan-identity check. This is what makes "which plan actually ran" answerable after the fact |
| `appliedByTool` | varchar | Which applier wrote it, and its version. The network may end up running either our own applier or CRMBuilder (that decision is due 2026-09-19), and a stamp that does not say which tool wrote it is ambiguous the moment both have ever been used |

Field names are **not** prefixed here: `FieldManager::create()` only prefixes on
a non-custom scope, and `CNetworkStandard` is itself custom. Type them exactly as
written.

**All six are plain scalars on purpose.** No enums (nothing to drift out of), no
links (nothing to cascade), no formulas (nothing to clobber a supplied value).
This entity must be the least interesting thing in the CRM.

### Making it read-only for staff

Mark the five machine-written fields **Read-only** in Entity Manager if you like
the belt-and-braces, but understand what that does and does not do: the Entity
Manager *Read-only* checkbox is a **UI parameter only and never blocks an API
write** — only `readOnlyAfterCreate` / `readOnlySaved` are enforced server-side.
So it stops a curious admin editing the row by hand in the interface, and it does
not stop the applier, which is exactly the arrangement wanted here.

---

## 2. Links

**None.** This entity links to nothing and nothing links to it.

Worth stating explicitly rather than leaving as an omission, because the Create
Link dialog's two Name boxes are inverted and have been got wrong four times in
this project — this is the one build where that trap cannot fire.

---

## 3. Who writes it, and when

Not a CRM configuration step — recorded here so the build is understood, and
because it is the reason `appliedAt` means what it does.

- The **applier** writes this row, and **only after a complete successful apply.**
- A **partial** apply must leave the previous stamp **untouched.** An instance
  claiming conformance it does not have is worse than one claiming nothing,
  because the fleet console believes it.
- Nothing else writes it. Not the app, not staff, not a migration.

---

## 4. ACL — the grant that is easy to forget

The application reads this row with the **org-wide API key** and nothing else.
That grant is the whole reason this entity was chosen over the alternatives, so
it is the thing to verify rather than assume.

1. Administration → Roles → the role attached to the intake/org-wide API user.
2. Add scope **Network Standard**: **read = `all`**. No create, no edit, no delete
   — the applier uses an admin account for those.
3. Leave every staff role alone. Nobody needs to see this.

---

## 5. Verification — do this before calling the build done

Run against crm-test first, with the **org-wide API key**, not an admin session.
An admin bypasses ACL entirely, so an admin check proves nothing about the grant
in § 4.

```
GET /api/v1/CNetworkStandard?maxSize=1
X-Api-Key: <org-wide key>
```

| Result | Means |
|---|---|
| **HTTP 200, `total: 0`** | **Correct.** The entity exists, the API key can read it, and nothing has been applied yet. This is the expected end state of this build |
| HTTP 403 | The § 4 role grant was missed. The entity is invisible to the app |
| HTTP 404 | The entity was not created, or was created under a different name — check for `CCNetworkStandard` |

Then confirm the name landed correctly, which is the failure this project keeps
repeating:

```
GET /api/v1/Metadata     →  entityDefs.CNetworkStandard
```

It must be `CNetworkStandard`, with six fields and an empty `links` block. If you
find `CCNetworkStandard`, delete and rebuild with the unprefixed name — do not
rename around it.

Only when all of the above passes on crm-test, repeat the entire build on
production and verify the same way.

---

## 6. What this unblocks

- `/healthz` gains a `crmConfig` block reporting `{version, appliedAt,
  fingerprint}` — null everywhere until an applier writes a row
  (`prds/chapter-network/TASKS.md` § R1).
- `/setup`'s environment-diff panel can compare the two instances' configuration
  versions, which is immediately useful with only two.
- The fleet console (Phase 5) gets half of the pair it identifies an instance by:
  `(releaseTag, standardVersion)`. The other half is a git tag, and this repo has
  none yet.
