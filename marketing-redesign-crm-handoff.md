# CRM handoff — the Marketing Management redesign (build plan § 7e.11)

Last Updated: 10-24-26 15:20 · Revision 1.0 — change log at the end.

**What changes:** five fields, three relationships and two enum options,
plus two read grants on the Marketing Admin Role. This is the one CRM
change the redesign needs (`prds/prospect-marketing/build-plan.md`
§ 7e.11), carrying rulings 104 to 111 (the ladder, the referrer, personal
outreach, the reply flag) with rulings 117 to 125 applied. Everything is
additive. Nothing is Read-only. Every piece is feature-detected, so the
application stays as it is until the field exists.

**Steps M2 to M5 of the redesign are not built until § 5's reads pass.**
M2 (the ladder) needs the four `CProspect` fields and the two `CProspect`
links; M5 (personal outreach) needs the rest.

**Verified against crm-test 10-24-26 14:58 to 15:05**, as the
configuration administrator (`crm.config`): every field and link below
read back absent from `GET /Metadata`; the touch's campaign link read back
NOT required; `CProspect.assignedUser` read back enabled; every role's
grants on the six entities read from `GET /Role`. Nothing was written.

## Where it stands

| CRM | State |
|---|---|
| crm-test | **Not applied.** Plan dry-run 10-24-26 15:03: 9 changes, 1 already correct, fingerprint `6bb03652454a`. Role script dry-run 15:06: exactly the two grants in § 4. Conformance baseline 15:10: 21 conformant, exit 0. |
| Production | Not started. Rides the arc's deferred production slot (Doug, 10-20-26: no slot until campaign testing is finished). |
| Boston | Not started. With its release. |

## 1. What the plan does — and what it was going to do and does not need to

`scripts/plans/marketing-redesign.json`, plan fingerprint `6bb03652454a`.
Applied by the plan file, never by hand.

### 1a. Fields

| Entity | Stored field name | Type | Label | Notes |
|---|---|---|---|---|
| `CProspect` (Lead) | `qualificationLevel` | Enum: empty, Identified, Contactable, Referred | *Level* | The level inside Qualified (ruling 105). Empty unless `leadStatus` is Qualified; the application keeps that rule. Default empty, not required |
| `CProspect` | `levelSetAt` | Date-Time | *Level set by hand at* | Written with `levelSetByHand` when a person sets the level (ruling 106) |
| `CProspect` | `referredByName` | Varchar, max length 150 | *Referred by (name)* | A referrer who is not a partner on file |
| `CProspect` | `replied` | Bool, default false | *Replied* | Set by the email sync, cleared by conversion (ruling 109) |
| `COutreachCampaign` (Outreach Campaign) | `vendorEmailId` | Varchar, max length 64 | *Constant Contact email id* | The email staff picked in Marketing Management (ruling 96); the send report reads results by it (ruling 124) |

All five entities are custom, so every name is stored exactly as typed.

### 1b. Relationships

| Stored on | Link | Type | Points at | Link stored on the other side |
|---|---|---|---|---|
| `CProspect` | `levelSetByHand` (*Level set by hand*) | many-to-one | `User` | `User.cLevelSetLeads` — typed `levelSetLeads`; EspoCRM adds the `c` because User is not a custom entity |
| `CProspect` | `referredByPartner` (*Referred by (partner)*) | many-to-one | `CPartnerProfile` | `CPartnerProfile.referredLeads` (*Referred leads*) |
| `CConversation` | `prospects` (*Leads*) | many-to-many, middle table `cConversationProspect` | `CProspect` | `CProspect.conversations` (*Conversations*) |

The conversation link copies the shape the three existing parent links
have (`CConversation.engagements` / `partnerProfiles` / `sponsorProfiles`,
each `hasMany` with a `cConversation<Entity>` middle table and `conversations`
on the far side — read from `entityDefs.CConversation.links` 10-24-26).
`comms/crm.PARENT_LINKS` gains `"CProspect": "prospects"` with the code.
The middle-table name is given in the plan on purpose: left to EspoCRM it
can differ between instances.

### 1c. Enum options and the cleared flag

- `COutreachTouch.channel` gains **Personal call** and **Personal email**
  (ruling 119). Its options today: Postcard, Email, SMS, Call. Adding is
  additive; nothing is removed.
- `COutreachTouch.outreachCampaign` **is already not required.** Ruling
  119 and § 7e.11 expected to clear a required flag; the field reads back
  `{"type": "link", "label": "Outreach Campaign"}` with no `required` on
  crm-test (both `GET /Metadata` and `Admin/fieldManager`, 10-24-26). The
  plan keeps a `fieldParams` entry setting it false, which the applier
  reports as *already correct* here and would clear it on an instance
  where it is set. The requirement lives in the application
  (`campaigns/service.py`), and M5 relaxes it there.

### 1d. What the plan does not touch, and why

- **`CProspect.assignedUser` is already enabled** (`{"type": "link",
  "required": false, "view": "views/fields/assigned-user"}`, 10-24-26).
  § 7e.11 said "enabled, if absent"; it is present. It is **not on the
  lead's detail layout** (read 10-24-26: Overview holds `name`, Details
  holds the 23 fields from `businessName` to `alreadyKnownCompany`). Ruling
  108's *Assign* is an application action, so the layout is left alone; see
  § 7.
- **Marketing Admin Role: Assignment Permission is already `all`** (applied
  with the Phase 1 roles). A lead can be assigned to any user; the
  application narrows it to Marketing Admin Team members (ruling 108).
- **No new field rule.** The Marketing Admin Role has edit `all` on
  `CProspect` and its only `CProspect` field rule is `leadCode` (read yes,
  edit no), so staff can edit every new field, which ruling 106 requires
  for *Set level*. `replied`, `levelSetAt` and `levelSetByHand` are
  application-written but harmless if a person edits them; they get no
  rule. **None of the five fields is Read-only** (ruling 40).
- **Mentor Role: unchanged**, as § 7e.11 says. It already reads
  `CProspect` all and `CConversation` own.

## 2. Naming

Every name in the plan is given unprefixed. The applier computes the stored
name: `CProspect`, `COutreachCampaign`, `COutreachTouch`, `CConversation` and
`CPartnerProfile` are custom, so their fields and links are stored as typed;
`User` is not, so its far-side link becomes `cLevelSetLeads`. The dry run
prints every stored name (§ 3 shows the expected lines). Never type a `C`
or `c` prefix into the plan.

## 3. Order on crm-test

Doug runs both steps; the session's classifier refuses an `--apply` to
Claude. Never between 04:00 and 05:00 UTC, the nightly restore.

1. The fields, links and options:

   ```
   scripts/prospect_crm_test.sh redesign
   ```

   Expected, in order: five `created field` lines (`CProspect.qualificationLevel`,
   `.levelSetAt`, `.referredByName`, `.replied`, `COutreachCampaign.vendorEmailId`),
   `field COutreachTouch.outreachCampaign already has {'required': False}`,
   three `created link` lines (`CProspect.levelSetByHand -> User.cLevelSetLeads`,
   `CProspect.referredByPartner -> CPartnerProfile.referredLeads`,
   `CConversation.prospects -> CProspect.conversations`), the enum line
   adding the two options, a rebuild, then the read-back `verified` lines.
   No `FAILED`. The applier refuses to run if the plan's fingerprint is no
   longer `6bb03652454a`.

2. The two read grants:

   ```
   scripts/prospect_crm_test.sh roles
   ```

   Expected under CHANGES: `set Marketing Admin Role: CConversation {read:
   (not set) -> own} - read back OK`, the same for `CCommunication {read:
   (not set) -> all}`, and `rebuild -> HTTP 200`. Everything else SKIPPED.

## 4. The role grants — two conformance cells

Applied by `scripts/migrate_outreach_roles.py`, which gained them 10-24-26.
Merge-only: it never lowers or removes a level.

| Role | Entity | Grant | Why |
|---|---|---|---|
| Marketing Admin Role | `CConversation` | read `own` (the other actions explicit `no`) | The lead's page lists the lead's conversations **as the user** (`comms/service.list_conversations`). The sync stamps the mailbox owner into the conversation's `assignedUsers` (`comms/crm.stamp_owners`), so `own` reaches exactly the assignee's own threads — ruling 118's shape, and the Mentor Role's |
| Marketing Admin Role | `CCommunication` | read `all` (the other actions explicit `no`) | The thread view reads the messages as the user (`comms/service.conversation_thread`). The Mentor Role holds the same; a message is reachable only through a conversation the user can read |

§ 7e.11 names only the `CConversation` read. The `CCommunication` read is
added because the code path reads both as the user — inferred from
`comms/service.py` and the Mentor Role's grants, not yet proved in a
browser; M5's live pass proves it. Creating conversations, stamping owners
and the lead link stay the application's, under the `CustomAppAPIRole`,
which already holds create/read/edit `all` on both entities and on
`CProspect` (a relate checks both sides; read 10-24-26).

The roles standard (`prds/chapter-network/roles-standard/`) gains these two
cells when production does. **Roles differ between the two CRMs with no
detector**: the role script must run on production in the same slot as the
plan, not later.

## 5. Proof it landed — before any M2 work

Claude runs these after Doug's two steps.

1. **The shape, from the data.** `GET Metadata` →
   `entityDefs.CProspect.fields.{qualificationLevel,levelSetAt,referredByName,replied}`,
   `entityDefs.COutreachCampaign.fields.vendorEmailId`: each present, the
   type in § 1a, no `readOnly`. `entityDefs.CProspect.links.levelSetByHand`
   → `belongsTo User`, foreign `cLevelSetLeads`;
   `entityDefs.CProspect.links.referredByPartner` → `belongsTo
   CPartnerProfile`, foreign `referredLeads`;
   `entityDefs.CConversation.links.prospects` → `hasMany CProspect`,
   `relationName cConversationProspect`, foreign `conversations`; and
   `entityDefs.CProspect.links.conversations` the mirror. No
   `User.levelSetLeads` and no `User.cCLevelSetLeads`.
   `entityDefs.COutreachTouch.fields.channel.options` ends with the two new
   values.
2. **The application's own credential reads and writes them.** As the
   org-wide API key, each answers HTTP 200 (`total` may be 0):
   - `GET CProspect?select=id,qualificationLevel,levelSetAt,levelSetByHandId,referredByPartnerId,referredByName,replied,assignedUserId&maxSize=1`
   - `GET COutreachCampaign?select=id,vendorEmailId&maxSize=1`
   - `GET CConversation/{id}/prospects?maxSize=1` on any existing
     conversation (200, empty list)
   - one write and read-back on one crm-test lead: set `qualificationLevel`
     to `Identified` and `replied` to `true`, read both back equal, then
     clear both. A read cannot prove a field is writable; this can.
3. **The grants read back.** As the configuration administrator,
   `GET Role/{Marketing Admin Role id}` → `data.CConversation.read` is
   `own` and `data.CCommunication.read` is `all`.
4. **The conformance check is unchanged.** `scripts/preflight_crm.py --json`
   before (taken 10-24-26 15:10: 21 conformant, exit 0) and after. The two
   should be identical: nothing here is in the standard yet.

A non-admin browser pass belongs to M2's and M5's live passes, as Mark
Marketing: *Set level* on a lead, then a personal email and its reply on
the lead's page.

## 6. The sandbox

**The new middle table is newer than the baseline, so the nightly reset
truncates it** (`reset_crm_sandbox.py` empties every record table the
golden dump lacks; `SANDBOX-RESET.md`). `c_conversation_prospect` is empty
until M5 attaches a reply, and the sync re-attaches on its next pass, so
that is tolerable until M5's live pass. **The new columns on `c_prospect`
and `c_outreach_campaign` are emptied the same way**: a level set during
the day is gone by morning. When M2 seeds levels on the demo leads,
`scripts/sandbox/seed_outreach_data.py` gains a stage for them and the
baseline is recaptured; that is M2's. The role grants survive (the role
table is kept).

## 7. Layouts — not in this handoff

The new fields land on no layout. The lead's detail layout on crm-test
holds neither `assignedUser` nor any of the new fields. The redesign's edit
surface is the application's lead page (ruling 113: *Set level*, *Assign*,
*Email*, *Log a call* are its actions), and ruling 117's sweep exists
because staff also edit **facts** in the CRM's screens, not the level.
Putting *Level*, *Referred by* and *Assigned User* on the CRM layout is a
decision for Doug, recorded in the build plan when made; the mechanism
would be an extension of `scripts/apply_lead_layouts.py`.

## 8. Production and Boston

**Production**, at the arc's deferred Sunday 17:00 UTC slot, by a human,
from inside the web container: the three environment lines at the top of
`scripts/apply_crm_plan.py`, then

```
scripts/plans/marketing-redesign.json --apply --production --expect 6bb03652454a
```

then `bash scripts/prospect_crm_prod.sh roles` (dry run: expect the two
grants among its changes), then `… roles apply`. Expect
`outreachCampaign already has {'required': False}` there too: production
was built from the same Phase 1 plan. Read production's roles first; the
grants in § 4 were read on crm-test.

**Boston**, with its release:

```
scripts/apply_plan.sh boston scripts/plans/marketing-redesign.json 6bb03652454a
```

then the role script with Boston's credential.

**M2 to M5 must feature-detect every field and link** (the house rule for
a CRM-facing feature). Until a CRM has them, the Leads tab shows
`leadStatus` alone, no level is placed, no lead is assigned, and the touch
keeps requiring a campaign.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-24-26 15:20 | Claude (Claude Code) | Written for build plan § 7e.11 with rulings 117–125 applied. Every item verified against crm-test's metadata and roles 10-24-26 (nothing written): all nine additions absent, `outreachCampaign` already not required, `assignedUser` already enabled, Assignment Permission already `all`. Plan `scripts/plans/marketing-redesign.json` dry-run: 9 changes, fingerprint `6bb03652454a`. Two read grants added to `scripts/migrate_outreach_roles.py`; its dry run shows exactly those two. `redesign` step added to `scripts/prospect_crm_test.sh`. Conformance baseline 21 conformant. Not applied. |
