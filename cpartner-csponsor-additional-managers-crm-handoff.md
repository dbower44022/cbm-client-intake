# CRM handoff — additional managers on partner and funder records

Last Updated: 10-12-26 14:10 · Revision 1.2

## 1. What this adds, in one sentence

A partner or funder record may name **additional CBM managers** beside its
manager, exactly as an engagement names co-mentors beside its mentor — so a
second person's mail with the record's contacts is captured on the record,
the record appears in their My Email, and they are invited to its sessions.

## 2. Status per CRM

| CRM | State |
|---|---|
| crm-test | **Done 10-11-26 13:46** (Doug, the applier; both links read back; live pass the same afternoon, `OPEN-ITEMS.md` #46) |
| production | **Done 10-12-26** — applied ~14:00 by Doug from inside the production web container (fingerprint `f2d6a41ea16c`, both links verified by the applier and read back from the droplet); the non-admin pass and the Entity Manager check matched the same afternoon (step page https://claude.ai/artifact/Lq7rbijp2bJVqizQR9TmGT) |
| Boston | **Prepared 10-14-26 22:00, awaiting Doug's go** — read-only probe: both links and both `CMentorProfile` reverses absent; the applier's dry run against Boston (as its administrator, from this computer through `scripts/apply_plan.sh boston scripts/plans/additional-managers.json`) printed the same fingerprint `f2d6a41ea16c`. Boston's image is v0.232.0, which predates the applier shipping in it, so the apply runs from this computer, not its web console. Step page https://claude.ai/artifact/Covmt3vPbZnvWpr8WdQBY6 (private, *Boston Release Changes*): sections 1–2 apply and check, 3–6 the Sunday release and the pass. Boston holds one mentor profile and no partner or funder records, so the add itself waits for its roster |

## 3. The change, as the applier makes it (preferred)

Plan file: `scripts/plans/additional-managers.json`. Two relationships,
nothing else.

| This entity | Link stored on it | Type | Foreign entity | Link stored on the foreign entity |
|---|---|---|---|---|
| `CPartnerProfile` | `additionalManagers` | many-to-many | `CMentorProfile` | `comanagedPartners` |
| `CSponsorProfile` | `additionalManagers` | many-to-many | `CMentorProfile` | `comanagedSponsors` |

Labels: *Additional Managers* on the record; *Co-managed Partners* /
*Co-managed Funders* on the mentor profile. Relation names
`cPartnerProfileMentorProfile` and `cSponsorProfileMentorProfile`.

From the repository root, with the admin credential in `.env` (crm-test):

```
PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/apply_crm_plan.py scripts/plans/additional-managers.json
```

Expect `WOULD CHANGE:` with the two `create link` lines and
`Plan fingerprint: f2d6a41ea16c`. Then the same line with
`--apply --expect f2d6a41ea16c` (production adds `--production`). The
applier reads both links back from the CRM's own metadata.

## 4. The same change by hand (only if the applier cannot run)

Entity Manager → **Partner Profile** → Relationships → Create Link. The
dialog's two Name boxes are inverted (see CLAUDE.md): the **left** panel is
Partner Profile, the **right** panel is the Foreign Entity, Mentor Profile.
Type: *Many-to-Many*. In the **right** panel's Name box type
`additionalManagers`, label *Additional Managers* (that is the link stored
on Partner Profile). In the **left** panel's Name box type
`comanagedPartners`, label *Co-managed Partners* (the link stored on Mentor
Profile). Save, rebuild. Repeat from **Sponsor Profile** with
`comanagedSponsors` / *Co-managed Funders*. Verify in `GET /Metadata` that
`entityDefs.CPartnerProfile.links.additionalManagers` exists and that
`entityDefs.CMentorProfile.links.comanagedPartners` points back at it.

## 5. Grants

None. The Partner Manager and Sponsor Manager roles already edit their
records, and relating a mentor profile is checked on both sides — the app
escalates a foreign-record denial to the provisioning administrator, the
co-mentor rule. The org-wide API role reads every entity involved.

## 6. What the application does once the link exists

Feature-detected per request: the Details tab's **CBM Contacts** card
offers *Select existing CBM contact…* and *Remove*; the Overview lists them;
the Gmail sync scope, My Email and the Drive folder grants follow the
reverse link. Nothing is visible on a CRM without the link.

## Change log

| Rev | Date | Author | Change |
|---|---|---|---|
| 1.3 | 10-14-26 22:15 | Claude (Claude Code) | § 2: Boston prepared — probe, dry run, the `scripts/apply_plan.sh` front door, the step page; apply awaits Doug's go. |
| 1.2 | 10-12-26 14:10 | Claude (Claude Code) | § 2: production done and passed; Boston the only instance owed. |
| 1.1 | 10-12-26 14:05 | Claude (Claude Code) | § 2: crm-test done; production's step page linked. |
| 1.0 | 10-11-26 13:40 | Claude (Claude Code) | First version, with the v0.251.0 build. |
