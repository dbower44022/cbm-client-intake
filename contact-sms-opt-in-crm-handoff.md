# CRM handoff — text message (SMS) opt-in on Contact

Last Updated: 10-15-26 01:50 · Revision 1.2 — see change log at the end.

One new field on Contact, `cSmsOptIn`: a person's consent to receive **text
messages** from the chapter, its own tick beside the existing email marketing
opt-in `cMarketingOptIn`, because the law treats a text differently from an
email (Doug's ruling 9, 10-14-26, `prds/prospect-marketing/rulings.md`). It is
written **true-only** by every door that captures the marketing opt-in today —
the five public intake forms, event registration — plus the postcard landing
page, each with wording that names texts; staff never tick it on a person's
behalf. A text campaign selects on a phone number held plus this tick.
EspoCRM's native `phoneNumberIsOptedOut` stays the per-number opt-out, the
sibling of the email one. Plan: `prds/prospect-marketing/build-plan.md` v0.3
§ 1.6 and § 7 Phase 1. Application: Phase 1 of that plan, not yet built.

**Additive.** One bool, default false, on an entity every role already reads.
Safe to apply ahead of the code that writes it: until the forms carry the tick
the field simply stays false.

## 0. Current state — read this first

| CRM | State | Evidence |
|---|---|---|
| crm-test | **Done 10-15-26 01:05** — applied by Doug through `scripts/prospect_crm_test.sh sms` (the applier with `--expect 0bc7219ab932`), `Contact.cSmsOptIn` read back as `{"type":"bool","isCustom":true}`; `entityDefs.Contact.fields.smsOptIn` empty; `GET /Contact?maxSize=1&select=cSmsOptIn` as the org-wide key 200 with `cSmsOptIn: false`; the field-level report shows no `fieldData` rule on any role. § 4 step 3, the non-admin tick in the CRM, is folded into Phase 1's step 13 (the public form writes it) — nothing in the CRM's own form exercises the field until a layout shows it, and no role can strip it (§ 3). **crm-test complete; soaking to the Sunday slot.** | This document's § 2 and § 4 output, 10-15-26 01:05–01:18. |
| Production | **Done 10-18-26** with the outreach change (step page https://claude.ai/artifact/DPDwikp24BWMsg2UZs3naF); `Contact.cSmsOptIn` read back as `bool` by the org-wide key from inside the web container, 10-18-26. | `scripts/prospect_crm_prod.sh verify`. |
| Boston | **Owed** — with the release that carries Phase 1. | *Inferred:* built from crm-test's files before this change. |

**No role on crm-test carries a field-level rule on Contact** (every role's
`fieldData` read as admin, 10-14-26, § 3 below), so nothing on crm-test can
strip a write to the new field. Production's roles have never been read for
this; § 3 says how.

## 1. The naming rules

Every name below is given **unprefixed**; EspoCRM prefixes it. Contact is not a
custom entity, so a field typed `smsOptIn` is stored **`cSmsOptIn`** — exactly
as `cMarketingOptIn` beside it was. The applier computes this; verify with
`GET /Metadata`, never by reading a label.

## 2. The automated path — the whole change

From the repository root, as the configuration administrator (credentials in
`.env` as `ESPO_ADMIN_BASE` / `ESPO_ADMIN_USER` / `ESPO_ADMIN_PASS`; in a
deployed container they are the web component's provisioning admin).

```bash
cd /home/doug/Dropbox/Projects/cbm-client-intake
```

Dry run, which changes nothing and prints the plan and its fingerprint:

```bash
PYTHONPATH=. uv run python scripts/apply_crm_plan.py scripts/plans/contact-sms-opt-in.json
```

It prints one line — `create field Contact.cSmsOptIn (bool)  [typed 'smsOptIn']`
— and the fingerprint. Then apply exactly that plan:

```bash
PYTHONPATH=. uv run python scripts/apply_crm_plan.py scripts/plans/contact-sms-opt-in.json --apply --expect 0bc7219ab932
```

The fingerprint is a hash of the work, not of the file: on a CRM without the
field it is **`0bc7219ab932`** (crm-test, 10-14-26; pinned by
`tests/test_apply_crm_plan.py`), so production's dry run should print the same
value. A target that is not crm-test also needs `--production`.

The applier rebuilds and reads the field back. Not between 04:00 and 05:00 UTC
on crm-test (the reset window).

**The field's label and tooltip name texts**, so the CRM's own form says what
the tick means: label *Text message (SMS) opt-in*; tooltip *Ticked when this
person agreed to receive text messages (SMS) from the chapter. A text campaign
selects on a phone number held plus this tick. Set by the public forms when the
person ticks the box that names texts; the email marketing opt-in beside it
does not imply it.* Nothing chapter-specific in either.

## 3. Role grants — no new scope, one field-level check

The field lives on Contact, which every role that matters already reads, so
**no scope grant changes**. What can still go wrong is **field-level access**:
a role with a `fieldData` rule on Contact silently strips a write to any field
the rule names at a lower level than the scope (HTTP 200, nothing stored —
`[[espo-field-acl-silently-strips-writes]]`). The tell is a newer field
saving while older ones do, or the reverse.

**The roles that edit Contact on crm-test** (read as admin 10-14-26 23:05;
production's set is different and has not been read — roles differ between the
two with no detector, runbook § 6):

| Role | Contact edit | Attached to | `fieldData.Contact` |
|---|---|---|---|
| Client Assignment Role | all | Client Administration Team | none |
| ClientMentorIntakeRole | all | no team, no user (dormant) | none |
| CustomAppAPIRole | all | the `customapps` API user — the application | none |
| Mentor Administration Role | all | Mentor Administration Team | none |
| Mentor Role | own | Mentor Team | none |
| Partner Manager Role | all | Partner Management Team | none |
| Sponsor Manager Role | team | Sponsor Management Team | none |

The Marketing Admin Role creates and reads Contact but does **not** edit it
(presenters design D1) and so is not in this table; the application writes the
tick as the intake API user, never as a Marketing Admin.

**How to confirm no role strips the field**, on any CRM, as an administrator:

```bash
PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/migrate_outreach_roles.py --field-acl-only
```

It lists every role that edits Contact or Account and, for each, its
`fieldData` on both — *no fieldData rule … nothing can be stripped*, or the
rule's fields with a `!` line for any that would strip `cSmsOptIn`,
`cFunnelStage`, `cEntryStage` or `cOutreachCampaign`. It changes nothing and
needs no `COutreach*` entity. The raw read behind it, per role:
`GET /Role/{id}` → `fieldData.Contact` (admin only — the org-wide key gets 403
on `Role`, not an empty result). A rule that would strip the field is a hand
edit on that role (Administration → Roles → the role → Field Level, Contact),
made on both instances in the same session.

## 4. Verification — read the data back

1. **The shape.** `GET /Metadata?key=entityDefs.Contact.fields.cSmsOptIn`
   answers `{"type":"bool","default":false,"isCustom":true,…}`. An empty body
   means the field is absent (a missing key is HTTP 200 with no body);
   `entityDefs.Contact.fields.smsOptIn` must be **empty** — a hit there means a
   name was stored unprefixed, which cannot happen through the applier.
2. **As the org-wide API key**, the credential the application runs on:
   `GET /Contact?maxSize=1&select=cSmsOptIn` is HTTP 200 and each row carries
   `cSmsOptIn: false`. (200 is right even with `total: 0`.)
3. **As a real non-admin, not an administrator**, in the CRM itself until the
   forms carry the tick: sign in as `partner.manager` (Partner Manager Role,
   Contact edit *all*), open any contact, add *Text message (SMS) opt-in* to the
   detail layout if it is not shown (Administration → Layout Manager →
   Contact → Detail, as admin, once), tick it, save; then read the record as
   the org-wide key and confirm `cSmsOptIn: true`. A tick that reads back
   false is a field-level strip (§ 3). Administrators bypass ACL, so an admin
   pass proves nothing.
4. Once Phase 1 ships: tick the SMS box on the public client-intake form on
   crm-test and submit — the Contact reads `cSmsOptIn` true; submit once more
   for the same email unticked — still true (true-only, build plan § 7 Phase 1
   step 13).

## 5. The training sandbox

The build plan (§ 7) says both Phase 1 handoffs add tables the nightly reset
truncates. **This one adds a column, not a table**: the reset rebuilds the CRM
from the Entity Manager files, so `cSmsOptIn` survives the night. What does
not survive is any tick made during the day — the rows are restored from the
snapshot — which is the normal case for every field on crm-test, not a defect.
No seeder or re-baseline step is owed for this change on its own; the
re-baseline the companion handoff owes (`coutreach-entities-crm-handoff.md`
§ 6) captures this column with it.

## 6. Then production

At the Sunday 17:00 UTC slot, by a human, from inside the deployed **web**
container (`[[do-app-console-scripting]]`): § 2 dry run, § 2 apply, § 3's
field-level report, § 4 steps 1 and 2. Step 3 as a real non-admin in
production's CRM. Record the result in § 0.

```bash
export ESPO_ADMIN_BASE="$ESPO_BASE_URL"
export ESPO_ADMIN_USER="$ESPO_PROVISION_USERNAME"
export ESPO_ADMIN_PASS="$ESPO_PROVISION_PASSWORD"
cd /app
PYTHONPATH=/app .venv/bin/python scripts/apply_crm_plan.py scripts/plans/contact-sms-opt-in.json
PYTHONPATH=/app .venv/bin/python scripts/apply_crm_plan.py scripts/plans/contact-sms-opt-in.json --apply --production --expect 0bc7219ab932
PYTHONPATH=/app .venv/bin/python scripts/migrate_outreach_roles.py --field-acl-only
```

The container must carry this commit (the plan file ships in the image under
`scripts/plans/`); check `/healthz` for the version first.

## 7. Then Boston

With the release that carries Phase 1: the same three runs against
`crm.bbmentors.org` with Boston's configuration administrator, from the build
computer using Boston's settings file
(`scripts/run_with_admin.py --env ~/.config/cbm-boston/boston.env …`).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.2 | 10-15-26 01:50 | Claude (Claude Code) | crm-test complete; the non-admin tick folded into Phase 1's live step 13. |
| 1.1 | 10-15-26 01:20 | Claude (Claude Code) | crm-test applied (Doug, 01:05, via `scripts/prospect_crm_test.sh sms` — the applier's `--apply` is refused to Claude by the session classifier) and read back; the non-admin tick owed. |
| 1.0 | 10-14-26 23:15 | Claude (Claude Code) | Written from the kickoff prompt `prospect-marketing-crm-handoff-prompt-v0.1.md` v0.1.4 after the crm-test dry run (fingerprint `0bc7219ab932`) and the admin read of every role's `fieldData`. Nothing applied. |
