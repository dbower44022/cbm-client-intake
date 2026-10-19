# CRM handoff — the lead model (prospect marketing rulings 41–50)

Last Updated: 10-19-26 11:47 · Revision 1.2 — change log at the end.

**What this changes.** Every record from an outside source is now a **lead**
with a **lead status** (Unqualified · Qualified · Disqualified · Converted) and
a **Lead Source**. A Company or Contact carries the stages **Prospect · Engaged
· Opportunity** after first contact. The lead entity is labelled **Outreach
Lead** in the CRM. Rulings 41–50 in `prds/prospect-marketing/rulings.md` are the
authority; build plan § 7a is the plan this handoff carries out (step 1 of
§ 7a.5).

**What it does not change.** No stored entity, field or link name. No option and
no field is removed by this handoff's automated steps — § 6 proposes the
removals for Doug to approve after the code release. The application code that
reads the new words is the next session (§ 7a.5 step 2).

## 1. The order, and why it is staged

| Step | What | crm-test | Production | Boston |
|---|---|---|---|---|
| § 3 | The plan: three new fields, five option lists | now | with the code release, Sunday 17:00 UTC | with its release |
| § 4 | Labels: Outreach Lead and its links | now | with the plan | with the plan |
| § 5 | The value move | with the code release | with the code release | with its release |
| § 6 | Removal of the old options and fields | after the code release, on Doug's approval | same | same |
| § 3a | The touch positions plan | with the code release | with the code release | with its release |
| § 7 | Layouts | with the code release | same | same |

Steps 3 and 4 are additive and labels only, so the code running today keeps
working: it reads its stage ladder from its own constants
(`campaigns/config.STAGES`), never from the CRM's option order, and the old
options all stay. The value move waits for the code release because the code
running today still writes the old words; moving values under it would be
undone by its next write.

## 2. What crm-test held on 10-19-26 (read as the CRM configuration admin)

- `CProspect.funnelStage` and `entryStage`: Unverified · Qualified · Lead · Warm
  Lead · Opportunity. `entryDoor`: State filing · List · Partner file.
  `sideExit`: (empty) · Already known · Unqualified · Do Not Contact · Declined
  · Stale. No `leadStatus`, `leadSource` or `leadStatusChangedAt`.
- `cFunnelStage` and `cEntryStage` on Contact and Account: the same five stages.
- Records: **0** `CProspect`; **0** Contacts and **0** Accounts holding any stage
  value. The nightly reset empties the lead table, so crm-test's value move has
  nothing to move. Production's count is the value move's dry run, run from its
  container before its slot (ruling 45).
- Links pointing at the lead: `Contact.cProspectRecords`,
  `Account.cProspectRecords`, `Account.cAlreadyKnownProspects`,
  `COutreachTouch.prospect`.

## 2a. Applied on crm-test — 10-19-26

§ 3 and § 4 applied by Doug at 10:55 through `scripts/prospect_crm_test.sh
leadmodel` and `leadlabels`. Verified: the applier read every change back; the
relabel's second dry run reads 0 to change; the org-wide API key reads
`CProspect` with the three new fields (200) and sees the four statuses; the
value move's dry run finds nothing to move; Mark Marketing (non-admin,
Marketing Admin Team) opened *Outreach Leads* and *Create Outreach Lead*. § 5
and § 7 wait for the code release; § 6 for Doug.

## 3. The plan — `scripts/plans/coutreach-lead-model.json`

Fingerprint on crm-test 10-19-26: **`6e228dbb7d33`**.

- `CProspect.leadStatus` — enum, default **Unqualified**, options Unqualified ·
  Qualified · Disqualified · Converted (ruling 49). Not Read-only (ruling 40).
- `CProspect.leadStatusChangedAt` — datetime.
- `CProspect.leadSource` — enum: State filing · List · Partner file · Mentor
  request · Volunteer application · Information request · Partner application ·
  Funder application · Event registration · Email (rulings 41, 48).
- `CProspect.sideExit` — options reordered with **Duplicate** first; Already
  known and Unqualified stay, last, until § 6.
- `cFunnelStage` / `cEntryStage` on Contact and Account — **Prospect · Engaged ·
  Opportunity** first; the four old values stay, last, until § 6.

From the repository root, against crm-test:

```bash
scripts/prospect_crm_test.sh leadmodel
```

(The wrapper runs `scripts/apply_plan.sh test` with the fingerprint pinned.)

The applier rebuilds and reads every change back. Production's run is from
inside the web container with its own fingerprint from a dry run there.

## 3a. The touch positions — `scripts/plans/coutreach-touch-positions.json`

Found by the code session (10-19-26): `COutreachTouch.stageAtTouch` records the
target's position when it is touched, and its options were the old ladder. It
gains **Unqualified**, **Prospect** and **Engaged** (a lead's status, or a
Company's or Contact's stage); the old values stay, last, until § 6. Additive.
Fingerprint on crm-test 10-19-26: **`6c2e1d42af30`**.

```bash
scripts/prospect_crm_test.sh touchpos
```

## 4. Labels — `scripts/relabel_outreach_lead.py`

Sixteen labels through Label Manager: the entity *Prospect* → **Outreach Lead**
(plural **Outreach Leads**); the three reverse links on Contact and Account
(*Prospect records* → **Outreach Leads**, *Already-known prospects* →
**Duplicate outreach leads**); the touch's link (**Outreach Lead**); the lead's
own links (*Promoted to company/contact* → **Converted to company/contact**,
*Already known as* → **Duplicate of company**). Dry run by default; `--apply`
writes; `--undo --apply` restores the labels read on crm-test before the change.

```bash
scripts/prospect_crm_test.sh leadlabels
```

## 5. The value move — `scripts/migrate_lead_model_values.py`

Dry run by default, org-wide API key, refuses to start until § 3 is applied. The
rules are in the script's docstring and its tests
(`tests/test_migrate_lead_model_values.py`). In short: a lead with a converted
record becomes Converted; the old Unqualified reason becomes the Disqualified
status; Unverified → Unqualified; Already known → Duplicate; `entryDoor` copies
to `leadSource`; on Contact and Account Unverified, Qualified and Lead →
Prospect, Warm Lead → Engaged. **A lead at Lead, Warm Lead or Opportunity with
no converted record is reported, never written** — no ruling gives it a status.
A lead at Qualified with neither a website nor an email becomes Unqualified
(ruling 42). The status is only ever raised from the default, so a re-run
cannot undo what the application set. **Touches** (added by the code session):
a touch on a lead moves Unverified → Unqualified and reports Lead, Warm Lead or
Opportunity for a human; a touch on a Company or Contact moves as their stages
do. Needs § 3a first.

```bash
scripts/prospect_crm_test.sh leadmove
```

## 6. Proposed removals — Doug decides, after the code release

Removing an option orphans any record still holding it, and deleting a field is
metadata-only (the column and its data stay). Both wait until the value move has
run on that CRM and its dry run reads zero records on an old value.

- Options: `CProspect.sideExit` *Already known*, *Unqualified*; `cFunnelStage`
  and `cEntryStage` on Contact and Account *Unverified*, *Qualified*, *Lead*,
  *Warm Lead*.
- Fields on `CProspect`: `funnelStage`, `entryStage`, `entryDoor` (ruling 49;
  `entryDoor` by the same rule, since ruling 41 retires "door").

## 7. Layouts — with the code release

The lead's list layout today shows `funnelStage`, `entryDoor`, `sideExit`,
`website`; its detail layout shows `funnelStage`, `entryStage`,
`stageChangedAt`, `entryDoor`. At the code release they become `leadStatus`,
`leadSource`, `sideExit`, `website` (list) and `leadStatus`,
`leadStatusChangedAt`, `leadSource` (detail), written through the admin layout
API by `scripts/apply_lead_layouts.py` (each retired field replaced where it
stands; `stageChangedAt` taken off; idempotent; dry run by default — on crm-test
10-19-26 the dry run listed the six replacements). Earlier, staff would see
empty fields the code does not yet write.

```bash
scripts/prospect_crm_test.sh leadlayouts
```

## 8. Verification, per CRM

1. The applier's read-back (§ 3) and the relabel script's second dry run, which
   must read *Nothing to do*.
2. As the org-wide API key: `GET CProspect?maxSize=1&select=leadStatus,leadSource`
   answers 200.
3. As a real non-admin Marketing Admin Team member in the CRM: open the Outreach
   Leads list and one Company, and see the new labels. An admin check proves
   nothing about this.
4. `scripts/preflight_crm.py` before and after, diffed.

## Revision control

| Field | Value |
|---|---|
| Document | CRM handoff — the lead model |
| Version | 1.2 |
| Last Updated | 10-19-26 11:47 |
| Prepared by | Claude (Claude Code), for D. Bower |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.2 | 10-19-26 11:47 | Claude (Claude Code) | The code session: § 3a (the touch positions plan, fingerprint `6c2e1d42af30`), § 5 extended to touches and to ruling 42's Qualified rule, § 7 written as `scripts/apply_lead_layouts.py`; the three steps are the `touchpos`, `leadmove` and `leadlayouts` words. |
| 1.1 | 10-19-26 11:03 | Claude (Claude Code) | § 2a: §§ 3 and 4 applied on crm-test and verified, including as a non-admin. |
| 1.0 | 10-19-26 10:54 | Claude (Claude Code) | First version: the state read on crm-test, the additive plan (fingerprint `6e228dbb7d33`), the relabel, the value move, the proposed removals and the layouts, each staged against the code release. |
