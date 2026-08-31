# Applier-coverage record — Lakeside rehearsal (2026-08-31)

Per configuration category: which mechanism carried it onto the throwaway
(EspoCRM 10.0.6, deployed by CRMBuilder DEP-001 / INST-001), and the outcome.
Source instance: crm-test (EspoCRM 9.3.4).

| Category | Carried by | Outcome | Notes |
|---|---|---|---|
| Entities (16 custom), fields, links, enum options | **File baseline** — crm-test `custom/Espo/Custom` (791 files, 3.6 MB) → rsync → `chown www-data` → `php command.php rebuild` | **Clean.** Rebuild in 3 s, no log errors; every crm-test custom field and link on the 24 entities that matter exists on the target; 16 custom entities match exactly | Needs a **shell on the droplet** — the CRMBuilder deploy gives none unless *Extra SSH keys* is ticked (F1). Destination path differs by installer version: crm-test `data/espocrm/custom`, 10.x installer `data/espocrm/persistent/custom` (F3). Crossed a major version (9.3.4 → 10.0.6) without incident (F2) |
| Formulas, logicDefs, clientDefs, aclDefs, entityAcl, recordDefs, selectDefs | File baseline | Carried (present in the tree) | **No API carrier exists in this repo** for any of these |
| Layouts (16 entities' list/detail/etc.) | File baseline | Carried | API write still untested — not needed while the file half exists |
| Labels (i18n) | File baseline | Carried verbatim | 10 distinct labels contain "CBM" (e.g. *CBM Email*, *CBM Client*, *CBM Manager*) — standard under ruling 4, but they are **content**, not identifiers (F7) |
| Orphan tables | — | The 16 `c_` tables crm-test has and the target does not are **all orphans** (double-C grant tables, seven `*_probe` tables, old attendee/co-mentor tables, `c_mentor`) | A build from files is cleaner than the instance it came from (F4) |
| Teams (9) | **API** — `apply_api_half.py` (`POST Team`) | Applied 9/9 | |
| Roles (12) incl. `data`, `fieldData`, 11 permissions | **API** (`POST Role`, read back and compared) | Applied 12/12, read-back identical | **First API write of roles here — it works.** But: **73 entries unapplyable** — 71 (role × scope) pairs naming extension scopes the target lacks (`Report`, `ReportCategory`, `BpmnFlowchart`, `BpmnProcess`, `BpmnUserTask`, `GoogleCalendar`, `GoogleContacts`) and 2 stale field-level entries (`Standard User` → `Account.cCompanyPartnerProfile`, a field deleted 2026-08-14). EspoCRM 10 refuses both outright (HTTP 400); the applier now strips and records them, exiting **4** per the contract (F5, F6) |
| Role → team attachments (7) | API (`POST Role/{id}/teams`) | Applied 7/7 | |
| Email templates | API (`POST EmailTemplate`) | Applied 2/2 (the two crm-test holds) | The five `Event*` templates are absent on crm-test too — preflight exits 1 on both instances identically |
| Org-wide API user `customapps` + `CustomAppAPIRole` | API (`POST User type=api authMethod=ApiKey`; key read back) | Applied; key minted into the env file | Role attached directly to the user, as on crm-test |
| Provisioning admin (`lakeside.provision`) | API (`POST User type=admin`) | Applied; password minted (alphanumeric) | |
| `CNetworkStandard` entity + read grant + no tab | File baseline (entity) + API (grant rides in `CustomAppAPIRole.data`; tab list via Settings) | `build_networkstandard.py` dry run: **nothing to do**; org key GET → HTTP 200, total 0 | Stamp **not written**: the apply ended exit 4, and C9 says the stamp follows a *complete* apply. `/healthz` will read `unstamped` — the honest value |
| Instance settings (§ E) + tab list + quick-create list | API (`PUT Settings`) | Applied; read back equal | Tab-list `url` item (Cleveland docs link) dropped as per-chapter. `timeZone` left Eastern — the app's § C hardcodes |
| Extensions (Advanced Pack 3.12.1, Google Integration 1.8.4 on crm-test) | **none** | **Not carried** | Paid / separately installed; the roles depend on their scopes (F5). Not in the standard as written anywhere |
| Duplicate checks, saved views, workflows | — | Not examined | Neither instance's state was read; still unverified either way |
| Users (non-admin), test data | Stage 4 | — | Per-chapter, not standard |

## Gate

- `preflight_crm.py --json` on the throwaway: **exit 1 — 20 conformant, 1 absent** (`EmailTemplate`: the five `Event*`), byte-for-byte the same result as crm-test's baseline run this morning.
- `sync_form_options.py` dry run: **exit 0** — all 16 managed lists match.
- `build_networkstandard.py` dry run: **exit 0** — nothing to do.

## Findings (numbered for TASKS.md)

- **F1** The CRMBuilder deploy leaves the services org without a shell on the droplet unless *Extra SSH keys* is ticked; the file half needs one. Fix for the runbook: tick it, or CRMBuilder exposes the run's key. One paste in the DO Droplet Console worked as the fallback.
- **F2** CRMBuilder installs the current EspoCRM (10.0.6); Cleveland runs 9.3.4. A chapter would start a major version ahead. The 9.x file baseline rebuilt cleanly on 10.x, but the release train needs a pinned version → CRMBuilder requirement.
- **F3** The installer's on-disk layout changed between versions (`persistent/custom`), so "copy the tree" needs the path resolved per installer, not hard-coded.
- **F4** crm-test carries 16 orphan tables; the standard built from files has none.
- **F5** The roles depend on extension scopes (Advanced Pack, Google Integration). Either the extensions are part of the standard (and a chapter licenses Advanced Pack), or the roles must be filtered per target. `apply_api_half.py` does the latter and exits 4. This is the contract's unapplyable case, observed live for the first time.
- **F6** crm-test's `Standard User` role holds a stale field-level entry for a deleted field; EspoCRM 10 rejects the whole role for it. A capture must be validated against the target's `entityDefs` before writing.
- **F7** Ten field labels in the i18n files carry "CBM". Standard by ruling 4 but visible to a Lakeside user as *CBM Email*. A `{{org}}`-style question for the CRM half.
- **F8** crm-test's nightly reset removed the `crm.config` admin account created 2026-08-27 (users reset unless re-baselined), so the skill's admin login is dead there; the roles capture was done from the database over SSH instead.

## CRMBuilder Audit cross-check (Doug, desktop, after Stage 2)

29 entities / 573 fields / 164 relationships / 257 layouts / **12 roles / 9 teams** — 0 drifted, 0 absent. Agrees with the conformance check and the metadata diff on everything both can see.

- **F9 (CRMBuilder)** Email-template listing fails with HTTP 400 on EspoCRM 10.0.6 for every parent type ("could not list email templates (HTTP 400); skipped"), so the audit reads 0 templates where 2 exist. Report to the CRMBuilder repo; not fixed here.
- **F10 (CRMBuilder)** "Standard User: field permission on Account.cClientProfile has no design field — skipped": a field-level role entry naming a link is skipped silently rather than flagged — same class as F6.

## Stage 4 preparation

Seven non-admin users created by API (`stage4_users.py`), one per gated team, `type=regular`; each signs in and `App/user` reports exactly its one team and no `rolesNames` — the ACL shape the product gates on. The Mentor Team user has a Contact + `CMentorProfile` (`assignedUsersIds` set; `assignedUserId` reads null, as on crm-test where the single assigned user is disabled).

- **F11 (Cleveland, → OPEN-ITEMS)** On crm-test only 7 of the 9 teams carry a role; **Analytics Admin Team** and System Administration Team have none. A user whose only team is Analytics Admin holds no CRM read grant at all.

## Stage 4 human pass (Doug, browser) — all "You should see" lines matched

Client-intake form submitted end to end; `lakeside.clientadmin` saw the engagement and assigned it to Jordan Mentor; `lakeside.mentor` saw it in Client Management and opened My Mentor Profile; `lakeside.marketing` saw the submission Completed/Closed in Submission Admin. Portal tiles matched each user's single team.

- **F13 — the standard has a THIRD half: client-side custom code.** `clientDefs/App.json` names `custom:views/site/navbar`, whose file lives at `client/custom/src/views/site/navbar.js` — outside `custom/Espo/Custom`, in a separate volume on the 10.x installer (`persistent/custom-client`). Without it the CRM's own UI renders a blank page (404 on the view). crm-test's `client/custom/` also holds the two extensions' client modules (`modules/google`, `modules/advanced`), which belong to the extensions and were deliberately not copied. Fixed by copying `client/custom/src/` (one file) + rebuild. The applier's file half must carry both trees.
