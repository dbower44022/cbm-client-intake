# CRM handoff — prospect marketing and Campaign Management (Phase 1): `CProspect`, `COutreachCampaign`, `COutreachTouch`

Last Updated: 10-15-26 01:50 · Revision 1.3 — see change log at the end.

Three new record types and the links that tie them to what the CRM already
holds. A **prospect record** (`CProspect`) is a quarantine for a business or
person the chapter cannot yet uniquely identify (Doug's ruling 21): it carries
the funnel rung, the entry rung, who or what qualified it, the side exit and
every touch made while it is a prospect; a web domain promotes the business to
a Company typed Prospect, an email promotes the person to a Contact typed
Prospect, and the promoted record links back. A **campaign**
(`COutreachCampaign`, labelled *Outreach Campaign* in the CRM since ruling 35 — the
application's screens keep *Campaign*, CM-11) is created by marketing
users in one of five kinds (CM-3), names the partners it is for (CM-2) and the
events it advertises (CM-6), and is what the records a form creates carry
(rulings 26 and 27). A **touch** (`COutreachTouch`) is one attempt to reach a
business or person, and a `Planned` touch in a `Running` campaign is what
"Active Prospect" means in storage (ruling 10). Beside them: the rung on
Contact and Account (§ 1.8 of the plan), the `Prospect` option on a company's
type, and — ruling 30 — a many-to-many `referringPartners` on the engagement
beside the single `referringPartner` of v0.255.0, so a client who arrives
through a campaign naming several partners is credited to every one of them.

Plan: `prds/prospect-marketing/build-plan.md` v0.3 § 1 (every name) and § 7
Phase 1 (the grants). Rulings: `prds/prospect-marketing/rulings.md`.
Application: Phase 1 of that plan, not yet built; it ships dark behind
`CAMPAIGNS_ENABLED` and feature-detects every link.

**Additive.** Three entities, 57 fields, 17 links, one enum option. Nothing is
removed, renamed or narrowed. Safe to apply ahead of the code.

## 0. Current state — read this first

| CRM | State | Evidence |
|---|---|---|
| crm-test | **Done 10-15-26 01:06–01:19.** § 2 applied by Doug through `scripts/prospect_crm_test.sh outreach` (the applier with `--expect 6b29c8928dcf`; the `--apply` is refused to Claude by the session classifier): 78 changes, 77 read back, no failure — **`mailingAddress` was accepted as the `address` type** (item (b) settled; sub-fields `mailingAddressStreet/City/State/Country/PostalCode` present). § 3.1 by Doug (`notes`): `description` reads `wysiwyg`. § 3.2 by Claude through the admin API (`PUT /Settings`): Prospects and Campaigns after Information Requests, Touches removed, read back. **Also done, not in the plan:** the three detail layouts carried only `name`, so every new field and many-to-one link was added to a *Details* panel and the list layouts gained five columns each, read back (the layout API, admin). § 4 applied by Doug (`roles`): six grants set and read back, every re-check already held, rebuild 200; **re-run 10-15-26 11:4x for the seventh grant**, `CustomAppAPIRole` edit on `COutreachCampaign` (the worker's run; v0.258.4). § 5 steps 1, 2, 4, 5 passed as the org-wide key (three 200s with `total: 0`; `scopes.CCProspect` empty; the sync dry run clean; the conformance diff before/after empty). § 5 step 3 **passed 10-15-26 01:49** — Doug as Mark Marketing (tabs, a Draft Postcard campaign, a Prospect with a mailing address, a Planned touch on it, the touch listed on the campaign) and as Sally Sponsor (no tabs, the list refused); the partner relate as Mark Marketing answered *operation requires edit access to foreign record*, the expected both-sides check (item (i)). **crm-test complete; soaking to the Sunday slot.** | This document's output, 10-15-26 01:06–01:19; Doug's pass 01:49 ("all steps passed"). |
| Production | **Owed** — Sunday 17:00 UTC slot, from inside the deployed web container, after crm-test has soaked. | *Inferred:* production has none of this; the dry run in § 2 proves it. |
| Boston | **Owed** — with the release that carries Phase 1. | *Inferred:* built from crm-test's files before this change. |

Nine things to know before the apply. The first was Doug's to rule on and
is ruled; the rest are decided here and said so.

**(a) One name in the plan's § 1.5 could not be stored as written — RULED
10-15-26 00:01, ruling 32: the drafted name `attributedPartnerProfiles`
stands; build plan v0.4 carries it; the plan file and fingerprint are
unchanged.** The table gave `COutreachCampaign.partnerProfiles` to two different
links: the many-to-many to `CPartnerProfile` (CM-2, the partners a campaign
names) **and** the reverse of `CPartnerProfile.outreachCampaign` (ruling 27,
the partner profiles a campaign's link created). EspoCRM refuses a second link
under a name an entity already has, so the second create would fail. The plan
file keeps `partnerProfiles` for the many-to-many — it mirrors
`CEvent.partnerProfiles`, the house pattern — and names the many-to-one's
reverse **`attributedPartnerProfiles`** (label *Partners created through this
campaign*). Cost: it no longer matches its sibling `sponsorProfiles` on the
funder side. The alternative is to rename both attribution reverses
(`attributedPartnerProfiles` and `attributedSponsorProfiles`) so the family
reads alike; one more line in the plan file, a new fingerprint. Doug chose the
drafted name (option 1); the alternative was not taken.

**(b) `mailingAddress` is built as EspoCRM's `address` type**, not four
varchars — **settled 10-15-26 01:12: crm-test accepted it and read it back.** Evidence: on crm-test `GET /Metadata?key=fields.address` reads
`notCreatable: false` (10-14-26), so the Field Manager offers it and the
applier's `POST Admin/fieldManager/CProspect` is the same call the dialog
makes; `Account.billingAddress` reads back as `{"type":"address"}`, which is
what § 5's verification will look for. **The dry run cannot prove acceptance**
— it makes no write — so this is the first `address` field the applier
creates, as `image` was on 10-08-26. If the apply reports that one field
FAILED, replace its entry in the plan file with five varchars —
`mailingStreet` (255), `mailingCity` (100), `mailingState` (100),
`mailingPostalCode` (40), `mailingCountry` (100), the sub-field lengths the
`address` type uses — re-run the dry run for the new fingerprint, apply
again (idempotent: everything already made is skipped), and record it here.
The address sub-fields the type creates are `mailingAddressStreet`,
`mailingAddressCity`, `mailingAddressState`, `mailingAddressCountry`,
`mailingAddressPostalCode`; the application writes those.

**(c) `COutreachCampaign.description` is `wysiwyg` in the plan, and the plan
file cannot make it so.** BasePlus ships `description` as `text`; the applier
skips an existing field and never changes a type. The conversion is the same
one-line droplet step that converted Funder Notes (§ 3.1). Until it runs, the
application's shared editor opens the plain box for it — it follows the live
type — so nothing breaks.

**(d) New entities land on the navigation tab list automatically, at the
end** — and confirmed 10-15-26: all three were appended, Touches included. `CEventPresenter`, created by the applier on 10-08-26, sits last in
crm-test's tab list (read as admin 10-14-26, after `CActionLog` in the
Organization group). So `Prospects` and `Campaigns` get their tab with no
step, in the wrong place, and `Touches` gets one the plan says it must not
have. § 3.2 is the hand step: move two, remove one.

**(e) `scanToken` "indexed" is not a Field Manager parameter.** `varchar`
takes `maxLength`, `pattern`, `default` and the like (read from
`fields.varchar.params`, 10-14-26); an index is an `indexes` entry in the
entity's custom `entityDefs` file plus a rebuild. The plan file sets
`maxLength: 16` and no index. The lookup is one filtered list read per scan;
add the index by hand only if a production scan proves slow.

**(f) `COutreachTouch.outreachCampaign` is "required" in the plan; the plan
file does not set it.** `createLink` takes no required flag and the applier
has no step for one. The application never creates a touch without its
campaign. A CRM-side tick (Administration → Entity Manager → Touch → Fields →
*Campaign* → Required) is optional and harmless; not owed.

**(g) Defaults the plan left open, decided here:** `campaignStatus` defaults
to `Draft`, `touchStatus` to `Planned`, `addressStatus` to `Usable`,
`scanCount` to `0`; `postcardSize` gains an empty first option so a campaign
that is not a postcard stores nothing, as `platform` does. The sign-off and
run stamps (`selectionRule`, `selectionSummary`, `pieceCount`,
`estimatedCost`, `signedOffByName`, `signedOffAt`, `runStartedAt`,
`runCompletedAt`) are marked **read-only**: a screen hint only, never a
permission (`[[espo-readonly-is-a-ui-param]]`); the application writes them
through the API regardless.

**(h) `estimatedCost` is a `currency` field.** EspoCRM creates
**`estimatedCostCurrency`** beside it; do not create that yourself. **Every
write of the amount must set the companion** or the save 400s
(`[[espo-currency-companion]]`, the contributions ledger's v0.123.2 lesson).

**(i) For the Phase 1 build, not this handoff:** the Marketing Admin Role
holds **no grant on Account at all** (read 10-14-26). The state-filing import
creates Companies typed Prospect (ruling 21), so either the import's Company
creates run under the intake API client — the quick-add precedent — or the
role gains Account create and read. The build session decides; nothing here
grants it. Also: a Marketing Admin relating a campaign to a partner needs
edit on the partner record (`[[espo-link-checks-both-sides]]`), which that
role deliberately lacks (Doug's ruling 2026-10-07); the events sponsors
picker's `_link_or_escalate` pattern is the answer, as it was there.

## 1. The naming rules

Every name below is given **unprefixed**; EspoCRM prefixes it by three
different rules, and the applier computes all of them.

| Typed | Where | Stored |
|---|---|---|
| `Prospect`, `OutreachCampaign`, `OutreachTouch` | Create Entity | `CProspect`, `COutreachCampaign`, `COutreachTouch` — entities **always** gain one `C` (typing `CProspect` would store `CCProspect`) |
| `funnelStage` | field on `CProspect` | `funnelStage` — a field on a custom entity is stored as typed |
| `funnelStage` | field on `Contact` or `Account` | `cFunnelStage` — a field on a native entity gains `c` |
| `outreachCampaign` | link on `CEngagement` | `outreachCampaign` |
| `outreachCampaign` | link on `Contact` or `Account` | `cOutreachCampaign` |
| `prospectRecords`, `alreadyKnownProspects`, `outreachTouches` | reverse links on `Account` and `Contact` | `cProspectRecords`, `cAlreadyKnownProspects`, `cOutreachTouches` |
| `companyType` | the enum option step on `Account` | `cCompanyType` — the plan file names the field unprefixed too; the applier resolves it |

The full typed-to-stored table is build plan § 1.10. The two entities called
*Campaign* in a dialog's Foreign Entity list are EspoCRM's own hidden
`Campaign` and ours; the API has no such ambiguity, which is one more reason
the whole build goes through it. Verify with `GET /Metadata`, never by reading
a label.

## 2. The automated path — the whole change

From the repository root, as the configuration administrator (credentials in
`.env` as `ESPO_ADMIN_BASE` / `ESPO_ADMIN_USER` / `ESPO_ADMIN_PASS`; in a
deployed container they are the web component's provisioning admin). The
applier is `scripts/apply_crm_plan.py` (committed since v0.241.2 so it ships
in the image); the plan file is `scripts/plans/coutreach-entities.json`, and it
is the written definition of the end state — every entity, field, link and
option, with its label and tooltip.

```bash
cd /home/doug/Dropbox/Projects/cbm-client-intake
```

Dry run, which changes nothing and prints the plan and its fingerprint:

```bash
PYTHONPATH=. uv run python scripts/apply_crm_plan.py scripts/plans/coutreach-entities.json
```

Read the 78 lines it prints: three entities, 21 fields on `CProspect`, 15 on
`COutreachCampaign`, 17 on `COutreachTouch`, two each on `Contact` and
`Account` (`cFunnelStage`, `cEntryStage`), the 17 links of § 2.1 and
`add enum options to Account.cCompanyType: Prospect`. Then apply exactly that
plan:

```bash
PYTHONPATH=. uv run python scripts/apply_crm_plan.py scripts/plans/coutreach-entities.json --apply --expect 6b29c8928dcf
```

The fingerprint is a hash of the work, not of the file: on a CRM that has none
of this change it is **`6b29c8928dcf`** (crm-test, 10-14-26; pinned by
`tests/test_apply_crm_plan.py`), so production's dry run should print the same
value. A target that is not crm-test also needs `--production`. A different
fingerprint means the plan file changed (item (a) ruled the other way, or the
address fallback of item (b)) or someone altered the CRM since — read the new
dry run before applying.

The applier creates the three entities, rebuilds, hangs the fields and links,
adds the option, rebuilds again and **reads every name back**: one `C` per
entity, each field under its stored name, each link pointing at the entity
intended. Expect a few minutes for 78 changes. Not between 04:00 and 05:00 UTC
on crm-test (the reset window).

### 2.1 The seventeen links, as the plan file states them

In the API there is no inversion: `link` is stored on `entity`, `linkForeign`
on `entityForeign`. These are the plan's § 1.5 rows in that form, stored names
shown.

| Stored on | Link | Type | Foreign entity | Foreign link | Relation (join table) |
|---|---|---|---|---|---|
| `CProspect` | `promotedCompany` | many-to-one | `Account` | `cProspectRecords` | — |
| `CProspect` | `promotedContact` | many-to-one | `Contact` | `cProspectRecords` | — |
| `CProspect` | `alreadyKnownCompany` | many-to-one | `Account` | `cAlreadyKnownProspects` | — |
| `COutreachTouch` | `outreachCampaign` | many-to-one | `COutreachCampaign` | `touches` | — |
| `COutreachTouch` | `prospect` | many-to-one | `CProspect` | `touches` | — |
| `COutreachTouch` | `contact` | many-to-one | `Contact` | `cOutreachTouches` | — |
| `COutreachTouch` | `company` | many-to-one | `Account` | `cOutreachTouches` | — |
| `COutreachCampaign` | `partnerProfiles` | **many-to-many** | `CPartnerProfile` | `sponsoredCampaigns` | `cOutreachCampaignPartnerProfile` |
| `COutreachCampaign` | `events` | **many-to-many** | `CEvent` | `outreachCampaigns` | `cOutreachCampaignEvent` |
| `CEngagement` | `referringPartners` | **many-to-many** | `CPartnerProfile` | `referredEngagements` | `cEngagementPartnerProfile` |
| `Contact` | `cOutreachCampaign` | many-to-one | `COutreachCampaign` | `contacts` | — |
| `Account` | `cOutreachCampaign` | many-to-one | `COutreachCampaign` | `companies` | — |
| `CEngagement` | `outreachCampaign` | many-to-one | `COutreachCampaign` | `engagements` | — |
| `CInformationRequest` | `outreachCampaign` | many-to-one | `COutreachCampaign` | `informationRequests` | — |
| `CEventRegistration` | `outreachCampaign` | many-to-one | `COutreachCampaign` | `eventRegistrations` | — |
| `CPartnerProfile` | `outreachCampaign` | many-to-one | `COutreachCampaign` | `attributedPartnerProfiles` — item (a) | — |
| `CSponsorProfile` | `outreachCampaign` | many-to-one | `COutreachCampaign` | `sponsorProfiles` | — |

None is one-to-one: the cardinality that has twice silently moved a record off
its owner is not used here. The three many-to-many links are **relationships**
in EspoCRM's sense — read through `list_related`, written with relate and
unrelate, never through a `*Ids` attribute on the record write
(`[[espo-custom-linkmultiple-is-a-relationship]]`). Their join tables are
named explicitly so the two instances cannot invent different ones.

## 3. Two hand steps after the apply

### 3.1 `COutreachCampaign.description` from text to wysiwyg

The same step that converted Funder Notes and the Client Administration notes
(`csponsorprofile-description-wysiwyg-crm-handoff.md`). It runs **on the CRM
droplet**, flips one key in the entity's custom `entityDefs` file with a
timestamped backup beside it, rebuilds, and reads the type back; text to
wysiwyg keeps the same column, so there is no data to migrate. From the
repository root, one line:

```bash
scripts/on_crm.sh test scripts/convert_notes_wysiwyg.sh COutreachCampaign
```

Expect `description was "text", now {"type":"wysiwyg"}` and, after the
rebuild, `COutreachCampaign.description: {"type":"wysiwyg"}`. Idempotent — a
second run reports *already wysiwyg* and writes nothing. Not between 04:00 and
05:00 UTC.

### 3.2 The navigation tab list

On crm-test this was done through the admin API (`GET /Settings`, the list
edited, `PUT /Settings {tabList}`, read back) — the same change the dialog
makes. By hand, as an administrator in the CRM: Administration → **User Interface** → the
**Tab List** panel. The three new entries are at the bottom, after
*Action Logs* and *Event Presenters* (item (d)).

1. Drag **Prospects** and **Campaigns** up into the first group, under the
   `$CRM` divider, after *Information Requests* and before *Events* — the
   order is a draft; any place in that group is right.
2. Remove **Touches** (the ✕ on its row). Touches are reached from a campaign
   and a prospect record, never from a tab (plan § 1.4).
3. Save.

Verify, as the same administrator: `GET /Settings` → `tabList` names
`CProspect` and `COutreachCampaign` and does **not** name `COutreachTouch`.
Or sign in as any non-admin and look at the top bar.

### 3.3 The detail and list layouts (found on the apply, not in the plan)

A new entity's default detail layout carries **only `name`** (and a list layout
of `name` alone), so a record form showed none of the new fields. On crm-test
each entity's detail layout gained a *Details* panel holding every plan field
and many-to-one link, and each list layout five columns (Prospect: name,
funnel stage, entry door, side exit, website; Campaign: name, kind, status,
start, end; Touch: name, channel, status, outcome, campaign), through the
layout API as admin (`GET/PUT {entity}/layout/detail` and `/layout/list`,
`[[espo-layout-api-readable]]`). Production and Boston need the same, or
Layout Manager by hand; the application's own screens do not depend on it.

### 3.4 The CRM labels — "Outreach Campaign" (ruling 35, found on the Phase 2 pass)

EspoCRM's own `Campaign` entity and its native `campaign` link on Contact and
Account are labelled *Campaign*, and the plan labelled ours the same — two
fields with one name on every Contact and Company, in the detail view, the
column picker, the filters, export and the report builder. Doug's ruling 35
(10-17-26): a custom field never takes a built-in field's name. Ours is
labelled *Outreach Campaign* in the CRM — the entity, its plural, and the
link and field on the eight records that carry it — by
`scripts/relabel_outreach_campaign.py` (Label Manager as admin, dry-run
default, idempotent; undo with `--label Campaign --plural Campaigns`).
crm-test done 10-17-26 22:49 (17 labels; a re-run reports none). Labels live
in the CRM's custom files, so the nightly reset keeps them.

## 4. The role grants — scripted, merge-only

`scripts/migrate_outreach_roles.py`, modelled on
`scripts/migrate_presenter_roles.py`. Roles are API-writable as an
administrator, so there are no hand steps here.

```bash
PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/migrate_outreach_roles.py
```

(Inside a container the three `ESPO_ADMIN_*` variables are exported from the
provisioning account instead, and the script runs directly.)

Dry run first (above), then `--apply`. It refuses to run before § 2 has
created the three entities (exit 2, after printing the field-level report).
**Idempotent and merge-only** — a level already at or above the wanted one is
skipped and nothing is ever lowered or removed. Every change is read back.

| Role | Scope | Grant | Why |
|---|---|---|---|
| **CustomAppAPIRole** (the `customapps` API user — the application) | `CProspect` | create yes · read all · edit all | the imports, the promotion links, the rung |
| | `COutreachTouch` | create yes · read all · edit all | the selection run, the scan, the vendor callback |
| | `COutreachCampaign` | read all · **edit all** | resolving a campaign id at delivery; the `partnerProfiles` relationship read (needs read on both ends — `CPartnerProfile` read is held); **the worker's run**, which moves the campaign to Running and Complete and stamps the run (edit added 10-15-26 after the live pass found the run refused with *No edit access*; re-run the script) |
| | `CEngagement` edit all · `CPartnerProfile` edit all · `Contact` edit all · `Account` edit all | **re-checks** | held on crm-test 10-14-26; named so a CRM that lacks one gains it rather than failing the `referringPartners` relate (both sides are checked) or a stage write |
| **Marketing Admin Role** (Marketing Admin Team — CM-1) | `CProspect`, `COutreachCampaign`, `COutreachTouch` | create yes · read all · edit all | marketing users create and run campaigns; **no delete** — a campaign is Cancelled |
| | `CEvent` read all · `CPartnerProfile` read all | **re-checks** | the events picker (CM-6) and the partners picker (CM-2); both held |
| | Assignment Permission | `all` | **re-check** — already `all` since 10-08-26. A role that creates a record the application leaves unassigned needs it: at *not set* or *team* EspoCRM refuses a record with neither a team nor an assigned user outright (read from `Acl/AssignmentChecker/Helper.php` on crm-test 10-08-26) |

Expected on crm-test: six `WOULD set` lines (the three new scopes on each
role) and every re-check under *SKIPPED (already correct)*. On production the
re-checks may differ — production's roles have never been read for this
(runbook § 6: roles differ between the two instances with no detector) — which
is exactly what the dry run is for.

**Field-level access is reported, never changed.** The script's first section
lists every role that edits Contact or Account with its `fieldData` on each;
on crm-test 10-14-26 all seven carry none. A `!` line names a rule that would
strip `cFunnelStage`, `cEntryStage`, `cOutreachCampaign` or the companion
handoff's `cSmsOptIn` — a hand edit on that role, on both instances in the
same session.

No new team. The Mentor Role gains nothing here; question 6 of the plan (who
makes the calls) may add `COutreachTouch` read and edit and `CProspect` read
to it later — noted as owed, not done.

## 5. Verification — read the data back

1. **The shape**, as any credential that reads metadata (the org-wide key will
   do), one request per entity:
   - `GET /Metadata?key=entityDefs.CProspect` — `fields` holds the 21 of § 2
     under their typed names plus `mailingAddress` of `type: address` (item
     (b)), and `links` holds `promotedCompany` → `Account`,
     `promotedContact` → `Contact`, `alreadyKnownCompany` → `Account`,
     `touches` → `COutreachTouch`.
   - `GET /Metadata?key=entityDefs.COutreachCampaign` — `fields` holds the 15
     plus `estimatedCostCurrency` (item (h)) and, after § 3.1,
     `description` of `type: wysiwyg`; `links` holds `partnerProfiles`
     (`hasMany`, `relationName: cOutreachCampaignPartnerProfile`), `events`
     (`cOutreachCampaignEvent`), `touches`, `contacts`, `companies`,
     `engagements`, `informationRequests`, `eventRegistrations`,
     `attributedPartnerProfiles`, `sponsorProfiles`.
   - `GET /Metadata?key=entityDefs.COutreachTouch` — the 17 fields; `links`
     holds `outreachCampaign` → `COutreachCampaign`, `prospect` →
     `CProspect`, `contact` → `Contact`, `company` → `Account`.
   - `GET /Metadata?key=entityDefs.CEngagement.links.referringPartners` →
     `{"type":"hasMany","entity":"CPartnerProfile","relationName":"cEngagementPartnerProfile",…}`,
     and `entityDefs.CPartnerProfile.links.referredEngagements` →
     `CEngagement`. `referringPartner` (singular) and its reverse
     `engagements` are unchanged.
   - `GET /Metadata?key=entityDefs.Contact.fields.cFunnelStage` and
     `…Account.fields.cFunnelStage` → `type: enum` with the five options;
     `entityDefs.Contact.links.cOutreachCampaign` → `COutreachCampaign`.
   - `GET /Metadata?key=entityDefs.Account.fields.cCompanyType` → `options`
     ends `…, "Other", "Prospect"`.
   - `GET /Metadata?key=scopes.CCProspect` must answer an **empty body** — a
     hit is a double prefix. The applier checks this itself.
2. **As the org-wide API key**, the credential the application runs on:
   `GET /CProspect?maxSize=1`, `GET /COutreachCampaign?maxSize=1`,
   `GET /COutreachTouch?maxSize=1` — each HTTP 200 (right even with
   `total: 0`). **A 403 means § 4 was missed** and the feature will be
   silently invisible to the application. `maxSize` above 200 is itself a
   403, so keep it at 1.
3. **As a real non-admin, not an administrator**, in the CRM itself until the
   application exists: sign in as **Mark Marketing** (Marketing Admin Team).
   The top bar shows *Prospects* and *Campaigns* and no *Touches* (§ 3.2).
   Create a Campaign — kind *Postcard*, status reads *Draft* by default — and
   in its *Partners* panel relate a sandbox partner; open that partner: its
   *Sponsored Campaigns* panel lists the campaign (the relate will need the
   admin fallback once the application does it, item (i); as a user in the
   CRM's own form it may 403 — a 403 here is the expected both-sides check,
   not a defect of the build). Create a Prospect with a mailing address and a
   website; create a Touch on it naming the campaign; the campaign's
   *Touches* panel lists it. Then sign in as `sally.sponsor` (no marketing
   seat): no *Campaigns* tab, and `GET /COutreachCampaign` as her answers
   403. Administrators bypass ACL, so an admin pass proves nothing.
4. **The form option lists.** `uv run python scripts/sync_form_options.py`
   (dry run) — `cCompanyType` is not one of the managed lists, so no drift is
   expected; a non-zero exit names what moved.
5. **The conformance check, before and after** (runbook § 3 steps 3 and 8):
   `scripts/preflight_crm.py --json` as the org-wide key, diffed — the diff
   should hold this change and nothing else.

## 6. The training sandbox

**This change adds six tables**, and the nightly reset truncates every table
newer than its baseline (`SANDBOX-RESET.md` § *Re-baseline*; the reset's own
log names them): `c_prospect`, `c_outreach_campaign`, `c_outreach_touch` and
the three join tables `c_outreach_campaign_partner_profile`,
`c_outreach_campaign_event`, `c_engagement_partner_profile`. The entities,
fields and links themselves survive — they live in files — but **every
prospect, campaign, touch and partner link made on crm-test vanishes at 04:00
UTC** until the baseline is recaptured. Owed, on a morning after a reset with
no release test running, once Phase 1 has something to seed: a seeder stage
for a showcase campaign and prospect, then `baseline --apply` on the droplet,
in the order that document gives. Until then a live pass on crm-test starts
again each morning, as the plan's § 7 step 14 says.

## 7. Then production

**The step page for the slot (written 10-18-26):** https://claude.ai/artifact/DPDwikp24BWMsg2UZs3naF
— the whole change as one word per step inside the web container,
`bash scripts/prospect_crm_prod.sh <whoami|sms|outreach|receipt|roles|labels|ui|verify> [apply]`
(fingerprints pinned in the script; `ui` is `scripts/apply_outreach_ui.py`, the
tab list and layouts of § 3.2–3.3 as a script; `verify` is § 5 steps 1–2 as the
org-wide key), plus the notes conversion from the build computer. Needs the
container on v0.260.3 or later. The detail below is the same change by hand.

At the Sunday 17:00 UTC slot, by a human, from inside the deployed **web**
container (`[[do-app-console-scripting]]`), § 2
dry run, § 2 apply, § 4 dry run, § 4 apply, § 5 steps 1 and 2; then § 3.1 from
the build computer (`scripts/on_crm.sh production scripts/convert_notes_wysiwyg.sh COutreachCampaign`)
and § 3.2 in production's CRM; then § 5 step 3 as a real non-admin. Record the
result in § 0. The container must carry this commit (the plan file and the
role script ship in the image); check `/healthz` for the version first.

```bash
export ESPO_ADMIN_BASE="$ESPO_BASE_URL"
export ESPO_ADMIN_USER="$ESPO_PROVISION_USERNAME"
export ESPO_ADMIN_PASS="$ESPO_PROVISION_PASSWORD"
cd /app
PYTHONPATH=/app .venv/bin/python scripts/apply_crm_plan.py scripts/plans/coutreach-entities.json
PYTHONPATH=/app .venv/bin/python scripts/apply_crm_plan.py scripts/plans/coutreach-entities.json --apply --production --expect 6b29c8928dcf
PYTHONPATH=/app .venv/bin/python scripts/migrate_outreach_roles.py
PYTHONPATH=/app .venv/bin/python scripts/migrate_outreach_roles.py --apply
```

Also at the same slot: **`scripts/plans/cintake-submission-prospect-response.json`**
(one enum option, `CIntakeSubmission.form` gains *Prospect Response*,
fingerprint `cb685b7372b1`) — the landing-page response's receipt vocabulary,
found while building Phase 1; without it the receipt is written without its
form, with a warning. And the three entities' **detail and list layouts**
(§ 3.3), which production's CRM needs exactly as crm-test did. And **the
labels** (§ 3.4): `PYTHONPATH=/app .venv/bin/python scripts/relabel_outreach_campaign.py`
then `--apply`, with the same three exports.

Production's `Held-Company` option (`OPEN-ITEMS.md` #11) and the intake API
role's Team read plus Assignment Permission (#16) are separate owed changes
and are not in this plan.

## 8. Then Boston

With the release that carries Phase 1: the same runs against
`crm.bbmentors.org` with Boston's configuration administrator, from the build
computer using Boston's settings file
(`scripts/run_with_admin.py --env ~/.config/cbm-boston/boston.env …` and
`scripts/on_crm.sh boston …`). Boston's `CHAPTER_KEY` is already `boston`;
nothing in any name here is chapter-specific.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.4 | 10-17-26 22:50 | Claude (Claude Code) | § 3.4 added: the CRM labels "Outreach Campaign" (ruling 35), crm-test done; production § 7 and Boston carry the step. |
| 1.3 | 10-15-26 01:50 | Claude (Claude Code) | The non-admin pass matched (Doug, 01:49): crm-test complete, soaking. The partner relate's refusal as a Marketing Admin recorded as the expected both-sides check. |
| 1.2 | 10-15-26 01:20 | Claude (Claude Code) | crm-test done: §§ 2, 3.1 and 4 run by Doug through `scripts/prospect_crm_test.sh` (the mutating runs are refused to Claude by the session classifier), § 3.2 and the new § 3.3 layouts through the admin API, § 5 steps 1, 2, 4, 5 passed; the address type accepted (item (b) settled); the non-admin pass owed. |
| 1.1 | 10-15-26 00:02 | Claude (Claude Code) | Item (a) ruled by Doug ("1", ruling 32): `attributedPartnerProfiles` stands. Nothing else changed; the fingerprint `6b29c8928dcf` is unaffected. |
| 1.0 | 10-14-26 23:15 | Claude (Claude Code) | Written from the kickoff prompt `prospect-marketing-crm-handoff-prompt-v0.1.md` v0.1.4 after the crm-test dry run (78 changes, fingerprint `6b29c8928dcf`) and the admin read of crm-test's roles and tab list. Nothing applied. Item (a), the `partnerProfiles` collision in build plan § 1.5, is put to Doug with a drafted name. |
