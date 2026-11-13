# CRM handoff — Business Evaluation phase 1: `CBusinessEvaluation`

Last Updated: 11-13-26 13:55 · Revision 0.2 — see change log at the end.

One new record type: one Business Evaluation record per evaluation area per
engagement, linked to the engagement, the client profile, the approving user
and the review session. Two new fields on the client profile hold the business
profile survey's answers. Plus two role grants: the org-wide API key's (phase 1) and the Mentor Role's (phase 2). Design:
`prds/business-evaluation-plan.md` § 5 (rulings BE7, BE9, BE14, BE17); build
prompt: `prompts/business-evaluation-phase1-prompt-v0.1.md`, step 5.

**Additive.** One entity, 18 fields on it, 2 fields on `CClientProfile`,
4 links, Multiple Assigned Users and Collaborators switched on, 2 role grants.
Nothing removed, renamed or narrowed. Safe ahead of the code: the application
feature-detects the entity and stays dark behind `BUSINESS_EVALUATION`.

## 0. Current state

| CRM | State | Evidence |
|---|---|---|
| crm-test | **Done 11-13-26** by Claude: `scripts/apply_crm_plan.py crm-plans/business-evaluation.json --apply --expect 89d89d28b53b` created and read back the entity, its settings, 20 fields and 4 links; `scripts/migrate_evaluation_roles.py --apply` set and read back the grant and rebuilt (HTTP 200). The org-wide key lists `CBusinessEvaluation` (HTTP 200, total 0); `scopes.CBusinessEvaluation` reads `assignedUsers: true`, `collaborators: true`. **Phase 2, 11-13-26**: the Mentor Role grant applied and read back (`{'create': 'yes', 'read': 'own', 'edit': 'own', 'stream': 'own', 'delete': 'no'}`), rebuild HTTP 200; the non-admin check passed — Doug, signed in as Joe Mentor, sent, read, expired and declined Brightline Bakehouse's evaluation. | The applier's and the role script's output. |
| Production | **Not applied.** At a Sunday 17:00 UTC slot, after crm-test's live check. | — |
| Boston | **Owed** with its release. | — |

Decided here, and said so:

- **No field is Read-only**, the draft report included: a Read-only field
  drops every API write, the worker's too (ruling 40). Phase 4 keeps reviewers
  off `draftReport` with a field rule on their roles.
- **`engagement` and `clientProfile` are required by the application, not the
  CRM.** The applier creates links after it sets field parameters, so it cannot
  mark a link required in the same run.
- **The entity is type Base with the stream on**: `status` is audited, and
  EspoCRM records audited changes in the stream.
- **Multiple Assigned Users and Collaborators are two separate settings**,
  switched on only by an entity update (`EntityManager/action/updateEntity`),
  never by creation. The plan's `entityParams` section does it; the applier
  learned that section for this change.
- **`name` is required by the Base type**, so the application names each
  record "{Area} — {Company}".
- **Grants:** `CustomAppAPIRole` create, read all, edit all. **Mentor Role**
  create, read own, edit own, stream own (phase 2): "own" is the role's level
  on `CEngagement`, read on crm-test, and with Multiple Assigned Users it
  reaches every record carrying the mentor in `assignedUsers`. Create lets a
  mentor's Send write the records as the mentor.
- **No sandbox seeder stage.** Business Evaluation records are made by tests;
  the nightly reset truncating them leaves nothing broken.

## 1. Names

`CBusinessEvaluation` (typed `BusinessEvaluation`; the CRM adds the `C`). Its
fields are stored exactly as written. The links on the three custom entities
are stored as typed: `CEngagement.businessEvaluations`,
`CClientProfile.businessEvaluations`, `CSession.businessEvaluations`. The link
on `User` gains a `c`: `User.cApprovedBusinessEvaluations`. The two client
profile fields are stored as typed: `evaluationProfile`, `evaluationProfileAt`.

## 2. Apply on crm-test (done 11-13-26)

From the build computer, in `~/Dropbox/Projects/cbm-client-intake`:

```
PYTHONPATH=. uv run python scripts/apply_crm_plan.py crm-plans/business-evaluation.json --apply --expect 89d89d28b53b
```

```
PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/migrate_evaluation_roles.py --apply
```

## 3. Verify

1. `GET /Metadata` → `entityDefs.CBusinessEvaluation`: the 18 plan fields plus
   `assignedUsers` and `collaborators`, none of the plan fields Read-only; links
   `engagement`, `clientProfile`, `approvedBy`, `reviewSession`.
   `entityDefs.User.links` carries `cApprovedBusinessEvaluations`.
2. `scopes.CBusinessEvaluation`: `assignedUsers` and `collaborators` both true.
3. As the org-wide key: `GET /CBusinessEvaluation?maxSize=1` answers 200.
4. A real non-admin pass: a Mentor Team member opens the Evaluations tab on
   their own engagement and sends an evaluation (done on crm-test 11-13-26).

## 4. Production and Boston

Production at a Sunday slot, from inside the production web container, after
the image carrying this release is deployed: the applier with this plan and
the fingerprint its own dry run prints there (production's CRM may differ from
crm-test, so the fingerprint is read there, not copied from here), then
`scripts/migrate_evaluation_roles.py --apply` under the admin login. Claude
writes the step page when the slot is booked. Boston:
`scripts/apply_plan.sh boston crm-plans/business-evaluation.json <fingerprint>`,
then the role script against Boston.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-13-26 01:32 | Claude (Claude Code) | Created. Applied and verified on crm-test the same day. |
| 0.2 | 11-13-26 13:55 | Claude (Claude Code) | Phase 2: the Mentor Role grant, applied on crm-test and checked as a real non-admin. |
