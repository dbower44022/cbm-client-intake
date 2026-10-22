# CRM handoff — the lead code in every link (rulings 71–75)

Last Updated: 10-22-26 12:50 · Revision 1.3 — change log at the end.

**What changes:** two text fields that hold a person's lead code, two
fields that count clicks on a touch, and two field rules on the Marketing
Admin Role. This is build plan § 7d.5 (`prds/prospect-marketing/build-plan.md`).
Rulings 71 to 74 (10-22-26) say every link sent to a known person ends in
that person's code, `/c/{link}/{code}`. The code belongs to the person for
life. It lives in the CRM, on the lead and on the contact.

**Nothing in D1 is built until § 4's reads pass as the org-wide API key.**

## Where it stands

| CRM | State |
|---|---|
| crm-test | **Fields applied 10-22-26 12:45** by Doug (`leadcode`: 4 created, 4 verified, `Clicked` already present). **§ 4 steps 1, 2 and 4 passed 12:47** as the org-wide key: shape as § 1, no stray `Contact.leadCode` or `cCLeadCode`; three reads 200; a write and read-back on one lead (Banter Beer and Wine) and one contact (Simone Achebe), both cleared after; conformance identical to the baseline. **Field rules applied 12:48** by Doug (`roles`; the same run also applied ruling 78's Marketing Admin Role User grant, read all / edit own, from a parallel session's uncommitted script edit, on Doug's choice). **§ 4 step 3 passed 12:50**: both rules read back as the configuration administrator `{read: yes, edit: no}`; an org-wide-key write to `leadCode` still stores. **crm-test complete. D1 may start.** |
| Production | Not started. Rides the arc's deferred production slot (Doug, 10-20-26: no slot until campaign testing is finished). |
| Boston | Not started. With its release. |

## 1. The fields — applied by the plan file, never by hand

`scripts/plans/lead-code.json`, plan fingerprint `bec909277859`.

| Entity | Stored field name | Type | Label | Notes |
|---|---|---|---|---|
| `CProspect` (Lead) | `leadCode` | Varchar, max length 16 | *Lead code* | Custom entity, so stored as typed |
| `Contact` | `cLeadCode` | Varchar, max length 16 | *Lead code* | Typed `leadCode` in the plan; EspoCRM adds the `c` because Contact is not a custom entity |
| `COutreachTouch` (Touch) | `firstClickedAt` | Date-Time | *First clicked at* | Written once, at the first click |
| `COutreachTouch` (Touch) | `clickCount` | Int, min 0, default 0 | *Click count* | Every click |
| `COutreachTouch` (Touch) | `outcome` | Enum — option `Clicked` | — | **Already present** on crm-test (built with the entity, 10-15-26). The plan checks it and skips it. Production and Boston were built from the same plan, so expect a skip there too |

Three things to know before applying.

- **None of these fields is Read-only.** A Read-only field is a global
  restriction that drops every API write, the application's included,
  with HTTP 200 (ruling 40). The application writes all four.
- **There is no index.** Ruling 74 says "indexed". *Index* is not a Field
  Manager parameter for a Varchar field — the same finding as the scan
  token's (`coutreach-entities-crm-handoff.md` item (e)). An index would be
  an `indexes` entry written into the CRM's custom metadata files on the
  droplet. The lookup is one filtered read per click, over a few thousand
  rows. Add the index by hand only if a production click proves slow.
- **The two code fields stay off every layout.** A new field lands on no
  layout. Leave it that way: the field rules in § 2 cover the Marketing
  Admin Role only, and five other roles can edit a Contact (§ 2).

## 2. The field rules — two conformance cells

Applied by `scripts/migrate_outreach_roles.py`, which gained them 10-22-26.
Its only restricting action: it adds *edit: no* on the named fields and
leaves every other rule alone.

| Role | Entity | Field | Read | Edit |
|---|---|---|---|---|
| Marketing Admin Role | `CProspect` | `leadCode` | yes | no |
| Marketing Admin Role | `Contact` | `cLeadCode` | yes | no |

**The rule binds the D1 code: every write of either field goes under the
org-wide API key.** A write under a Marketing Admin user's own login is
dropped silently, HTTP 200, by the rule above. That covers minting, *New
code*, the postcard run, and the copy from lead to contact at promotion.
The `CustomAppAPIRole` carries no field rule and already edits both
entities (re-checked by the role script's dry run).

**What the dry run found about Contact** (10-22-26, crm-test). The
Marketing Admin Role has no edit on Contact at all, so its Contact cell
blocks nothing today. It guards against a later grant. Five staff roles
can edit a Contact and carry no rule:

- Client Assignment Role — all
- Mentor Administration Role — all
- Partner Manager Role — all
- Sponsor Manager Role — team
- Mentor Role — own

The sixth, `ClientMentorIntakeRole`, is the intake API client. It must keep
edit, because public forms may write the code at promotion. What keeps the
five staff roles off the field is its absence from every layout. **Ruled
10-22-26 (ruling 77, option A): the rules stay on the Marketing Admin Role
only, and both code fields stay off every layout.** Adding either field to
a layout is a change to this ruling, not a layout tweak.

No role carries any `fieldData` rule on Contact or Account today, so
nothing an existing rule could strip.

## 3. Order on crm-test

Doug runs both steps; the session's classifier refuses an `--apply` to
Claude. Never between 04:00 and 05:00 UTC, the nightly restore.

1. The fields:

   ```
   scripts/prospect_crm_test.sh leadcode
   ```

   Expected: four `created` lines, `enum COutreachTouch.outcome already
   offers Clicked`, a rebuild, and four `verified` lines. No `FAILED`.

2. The field rules:

   ```
   scripts/prospect_crm_test.sh roles
   ```

   Expected under CHANGES: `set Marketing Admin Role: CProspect fields
   leadCode -> {'read': 'yes', 'edit': 'no'} - read back OK`, the same for
   `Contact fields cLeadCode`, and `rebuild -> HTTP 200`. Everything else
   SKIPPED.

## 4. Proof it landed — before any D1 work

Claude runs these after Doug's two steps.

1. **The shape, from the data.** `GET Metadata` → `entityDefs.CProspect.fields.leadCode`,
   `entityDefs.Contact.fields.cLeadCode`, `entityDefs.COutreachTouch.fields.firstClickedAt`
   and `.clickCount`. Each present, with the type in § 1 and no `readOnly`.
   No `Contact.cCLeadCode` and no `Contact.leadCode`.
2. **The application's own credential reads them.** As the org-wide API
   key, each answers HTTP 200 (`total` may be 0):
   - `GET CProspect?select=id,leadCode&maxSize=1`
   - `GET Contact?select=id,cLeadCode&maxSize=1`
   - `GET COutreachTouch?select=id,firstClickedAt,clickCount&maxSize=1`
   - one write and read-back: set `leadCode` on one crm-test lead under the
     API key, read it back equal, then clear it. This proves the field is
     writable, which a read cannot.
3. **The rule reads back.** As the configuration administrator,
   `GET Role/{Marketing Admin Role id}` → `fieldData.CProspect.leadCode`
   and `fieldData.Contact.cLeadCode` both `{read: yes, edit: no}`.
4. **The conformance check is unchanged.** `scripts/preflight_crm.py --json`
   before (taken 10-22-26 01:41: 20 conformant, 1 absent — five event email
   templates, a known gap unrelated to this change) and after. The two
   should be identical.

A non-admin browser pass is not needed for this handoff: no person edits
these fields. It belongs to D1's live pass, as Mark Marketing, where *New
code* and a click are tried end to end.

## 5. The sandbox

Role rules survive the nightly restore (the role table is kept). **The
field values do not.** The restore puts every record back as it was in the
baseline, so a code minted on crm-test during the day is gone by morning,
and a link made with it then opens the campaign with no lead on it. Ruling
74's reason for the CRM over an application table holds only for codes in
the baseline. **After D1 mints codes for the demo leads, the baseline is
recaptured** (`SANDBOX-RESET.md`), or a seeder stage mints them each night.
That choice belongs to D1.

## 6. Production and Boston

**Production**, at the arc's deferred Sunday 17:00 UTC slot, by a human,
from inside the web container: the three environment lines at the top of
`scripts/apply_crm_plan.py`, then

```
scripts/plans/lead-code.json --apply --production --expect bec909277859
```

then `bash scripts/prospect_crm_prod.sh roles` (dry run: expect the two
field rules among its changes), then `… roles apply`. Production's roles
must be read first: the five-role finding in § 2 is crm-test's. The roles
standard (`prds/chapter-network/roles-standard/`) gains the two cells when
production does.

**Boston**, with its release:

```
scripts/apply_plan.sh boston scripts/plans/lead-code.json bec909277859
```

then the role script with Boston's credential.

**D1 must feature-detect the two code fields** (the house rule for a
CRM-facing feature). Until a CRM has them, no code is minted, a
`/c/{link}/{code}` link opens the campaign with no lead, and the forms
behave as today.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.3 | 10-22-26 12:50 | Claude (Claude Code) | crm-test: field rules applied and read back; crm-test complete. |
| 1.2 | 10-22-26 12:47 | Claude (Claude Code) | crm-test: fields applied by Doug and read back as the org-wide key. |
| 1.1 | 10-22-26 12:40 | Claude (Claude Code) | § 2: ruling 77 recorded — rules on the Marketing Admin Role only, fields off every layout. |
| 1.0 | 10-22-26 01:42 | Claude (Claude Code) | Written for build plan § 7d.5, rulings 71–75. Plan dry-run on crm-test, 4 changes, fingerprint `bec909277859`; `Clicked` found already present. Two field rules added to `scripts/migrate_outreach_roles.py`, dry run shows exactly those two. No index (not a Field Manager parameter). Conformance baseline taken. |
