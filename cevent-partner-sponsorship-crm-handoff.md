# CRM handoff — partners on events become many-to-many, plus the notice-campaign identifier (Phase A)

Last Updated: 10-07-26 03:45 · Revision 1.1 — see change log at the end.

**What this changes:** an event can carry **many partners**, through one
many-to-many link that mirrors the funder link the event already has; the old
single *Partner Host* link is removed; and the event and the registration each
gain a text field for the identifier of the mailing-service campaign that
announced the event. Plan and rulings:
`prds/mailing-list-and-event-sponsorship-plan.md` (ruling 9 and § 5 Phase A).

**The application is already safe without it, and safe with it.** The
application reads neither the old link nor the new one today, so nothing
changes on any screen until the Phase B code ships, and that code
feature-detects the link. The change can be applied to each system in its own
time.

**Every claim below was read from crm-test on 2026-10-07 03:30 local** as the
configuration administrator account (`GET /Metadata`, the layout endpoints and
a list of `CEvent`), except where a line says *inferred*.

---

## 0. Current state — read this first

| System | State | Evidence |
|---|---|---|
| crm-test | **§ 2, § 4 and § 7 done 2026-10-07 07:39–07:40 UTC**, by the shipping applier as the configuration administrator: both fields and the link created, rebuilt, read back on both sides (relation `cPartnerProfileEvent`), the one demo host carried, all re-verified as the org-wide API key. Marketing Admin Role given `read: all` on both profiles and read back. **§ 5 (the hand removal of `partnerHost`) is still owed — Doug.** State before the change: | `CEvent.partnerHost` is `belongsTo → CPartnerProfile`, reverse `CPartnerProfile.hostedEvents`. The funder link is `CEvent.sponsorProfiles` ↔ `CSponsorProfile.sponsoredEvents`, relation table `cSponsorProfileEvent`. Neither `partnerProfiles` nor `noticeCampaignId` exists. **One** of crm-test's five events has a partner host (*Hiring Your First Employee* → *Cuyahoga Small Business Alliance*, demo data). No list, detail or relationships layout names either link. |
| Production | **Owed** — Sunday 17:00 UTC slot | *Inferred:* the same two links, because production's `partnerHost` was rebuilt to match crm-test on 2026-08-08 (`OPEN-ITEMS.md`, the reversed-link note). Production's events carry no partner host as far as is known; the dry run in § 4 is what proves it. |
| Boston | **Owed** — with the release that carries the Phase B code | *Inferred:* built from crm-test's files, so expected to hold `partnerHost` too. |

crm-test's schema changes survive the nightly reset: they are Entity Manager
work, which lives in files the reset rebuilds from. **The carried link value
(§ 4) does not** — the reset restores the data snapshot, so on crm-test the
one demo host is carried again on each re-run and nothing is lost either way.

## 1. The naming rules

`CEvent`, `CEventRegistration` and `CPartnerProfile` are all custom entities,
so **every name in this change is stored exactly as typed**: `partnerProfiles`,
`sponsoredEvents`, `noticeCampaignId` — no `c` prefix on any of them. The plan
gives the names unprefixed and both appliers compute the stored name. Nothing
here touches a non-custom entity.

The new link's far side is deliberately named **`sponsoredEvents`**, the same
word the funder side already uses, so the Phase B code reads one link name for
both domains. The relation table is named explicitly, `cPartnerProfileEvent`,
mirroring the funder's `cSponsorProfileEvent`; left unnamed, EspoCRM invents
one, and it would differ between systems.

## 2. The automated path — use this for everything but the removal

The change is defined once, in `scripts/plans/cevent-partner-sponsorship.json`.
`scripts/migrate_event_sponsorship_schema.py` applies that file's two fields and
one link: idempotent (anything present is skipped), additive only, then a
rebuild and a read-back of every change from metadata, including a check that
the link landed on the side intended. Every system it runs on ends with the
same schema. It never removes anything — § 5 is a hand step.

**On crm-test**, from this repository, with the configuration administrator
credential in `.env` (never `source .env` — the launcher parses it):

```bash
cd /home/doug/Dropbox/Projects/cbm-client-intake
```

```bash
PYTHONPATH=. uv run python \
  .claude/skills/espo-crm-changes/scripts/run_with_admin.py \
  scripts/migrate_event_sponsorship_schema.py --carry-host
```

That is the dry run. It was run on 2026-10-07 03:35 and printed exactly:

```
WOULD create field CEvent.noticeCampaignId (varchar)
WOULD create field CEventRegistration.noticeCampaignId (varchar)
WOULD create link CEvent.partnerProfiles <-> CPartnerProfile.sponsoredEvents (manyToMany, relation cPartnerProfileEvent)
WOULD carry 'Hiring Your First Employee' host 'Cuyahoga Small Business Alliance' into CEvent.partnerProfiles
1 host value(s) would be carried
```

**If it lists anything else, stop.** Then apply exactly that:

```bash
PYTHONPATH=. uv run python \
  .claude/skills/espo-crm-changes/scripts/run_with_admin.py \
  scripts/migrate_event_sponsorship_schema.py --carry-host --apply
```

The CRM-changes skill's own applier takes the same plan file and gives the
same result for the fields and the link (it does not carry the host value).
Its dry run on 2026-10-07 reported fingerprint `698a898a804b`; apply with
`--apply --expect 698a898a804b` if you use it instead.

**On production**, run the shipping script from inside the deployed **web**
container (the only place the production administrator credential exists),
never from a laptop — see the `do-app-console-scripting` note in `CLAUDE.md`:

```bash
export ESPO_ADMIN_BASE="$ESPO_BASE_URL"
export ESPO_ADMIN_USER="$ESPO_PROVISION_USERNAME"
export ESPO_ADMIN_PASS="$ESPO_PROVISION_PASSWORD"
```

```bash
PYTHONPATH=/app python scripts/migrate_event_sponsorship_schema.py --carry-host
```

```bash
PYTHONPATH=/app python scripts/migrate_event_sponsorship_schema.py --carry-host --apply
```

The container must be running a build that includes this change, or the
script and plan are not there.

## 3. What the plan builds

For a reader checking by eye.

| Entity | Field | Type | Details | Label |
|---|---|---|---|---|
| CEvent | `noticeCampaignId` | Varchar | max length 100, read-only on screen | Notice campaign ID |
| CEventRegistration | `noticeCampaignId` | Varchar | max length 100, read-only on screen | Notice campaign ID |

| Link stored on | Name | Type | Points at | Far-side name (stored on the far entity) | Relation table |
|---|---|---|---|---|---|
| CEvent | `partnerProfiles` | Many-to-Many | CPartnerProfile | `sponsoredEvents` | `cPartnerProfileEvent` |

Read-only on these two fields is a screen setting, not a permission: the
application writes them through the API, and staff should not hand-edit them.

## 4. Carry the old host values into the new link — before § 5

`--carry-host` reads every event with a `partnerHost` and adds that partner to
the event's new `partnerProfiles` link (idempotent — a partner already there
is skipped). Do this **before** removing the old link, because once the link
is gone the API can no longer read the value, even though the column keeps it.

On crm-test the dry run names one event (above). On production the dry run
should say `0 host value(s) would be carried`. **If it names any event, read
the list before applying** — those are real sponsorships that must come
across, and the fact that production holds them is itself worth knowing.

## 5. Remove the old single link — by hand, after § 2 and § 4

Removing a relationship is never automated here, by rule: it is destructive
in ways that look like success. It is also **metadata-only** — the
`partner_host_id` column and its values stay in the database, so a wrong
removal is recoverable by recreating the link under the **same** name.

1. Administration → **Entity Manager** → click **Event** → click
   **Relationships**.
2. Find the row whose **Link** column reads `partnerHost` and whose
   **Foreign Link** column reads `hostedEvents`. It points at *Partner
   Profile*.
   **Trap — three rows on this screen point at a partner or funder profile,
   and two of them have a far side named `sponsoredEvents`.** The funder row
   (`sponsorProfiles` / `sponsoredEvents`) and the new partner row
   (`partnerProfiles` / `sponsoredEvents`) both stay. The only row to remove
   is the one whose Link reads **`partnerHost`**.
3. Click ▾ at that row's far right → **Remove** → confirm. This deletes both
   sides (`CEvent.partnerHost` and `CPartnerProfile.hostedEvents`).
4. Administration → **Clear Cache**, then **Rebuild**.

No layout references the old link on either entity (read 2026-10-07), so
there is nothing to tidy on the Event or Partner Profile screens afterwards.

## 6. Verification — read the data back

As the **org-wide API key**, on the system just changed:

```
GET /api/v1/Metadata?key=entityDefs.CEvent.links.partnerProfiles
    -> {"type":"hasMany","entity":"CPartnerProfile","foreign":"sponsoredEvents",
        "relationName":"cPartnerProfileEvent", ...}
GET /api/v1/Metadata?key=entityDefs.CPartnerProfile.links.sponsoredEvents
    -> {"type":"hasMany","entity":"CEvent","foreign":"partnerProfiles", ...}
GET /api/v1/Metadata?key=entityDefs.CEvent.links.partnerHost
    -> null            (after § 5)
GET /api/v1/Metadata?key=entityDefs.CEvent.fields.noticeCampaignId
    -> {"type":"varchar","maxLength":100, ...}
GET /api/v1/Metadata?key=entityDefs.CEventRegistration.fields.noticeCampaignId
    -> {"type":"varchar","maxLength":100, ...}
GET /api/v1/CEvent/<an event id>/partnerProfiles?maxSize=1
    -> 200             (a total of 0 is correct on production)
```

The two `hasMany` answers with each naming the other as `foreign` are the
proof the link sits on the side intended. If either side answers `null`, the
link was built reversed or not at all — read `entityDefs.CEvent.links` and
`entityDefs.CPartnerProfile.links` in full before touching anything.

On crm-test, additionally: `GET /api/v1/CEvent/<the Hiring Your First Employee
id>/partnerProfiles` lists *Cuyahoga Small Business Alliance* — the carried
value.

## 7. Role grants — ruled and applied on crm-test; production and Boston owed

The schema needs no new grant: the organisation-wide API role already reads
and edits `CEvent`, `CEventRegistration`, `CPartnerProfile` and
`CSponsorProfile` at "all" (roles standard, `prod-capture-2026-08-31.json`).

**But Event Administration writes as the signed-in user, and the Marketing
Admin Role holds no access to `CPartnerProfile` or `CSponsorProfile` at all**
(same capture). Two consequences for the Phase B pickers, neither of which
this schema change causes but both of which it exposes:

- The partner and funder **pickers would list nothing** for a Marketing Admin
  user — a 403 swallowed by a best-effort read looks exactly like "no
  partners exist".
- **Relating** a partner to an event needs edit on the partner record too
  (`noAccessToForeignRecord`), so the write would be refused.

**Doug's ruling (2026-10-07): the Marketing Admin Role gets `read: all` on
`CPartnerProfile` and `CSponsorProfile`** (create / edit / delete / stream all
`no`). Applied on crm-test the same day through `PUT Role/{id}` as the
configuration administrator, read back, cache cleared; the role held no entry
for either scope before. Production and Boston get the same two cells with
their Phase A apply, and the roles standard capture must gain them when
production does. The pickers list because of this, and the plan is to have
the Phase B code make the link write through the existing user-first,
admin-on-foreign-denial path (`sessions.service._link_or_escalate`), so the
role never needs edit on records it does not manage. The cost is one more
place the admin service account acts on a user's behalf; every such write is
action-logged.

Roles differ between crm-test and production with no automatic detector, so
whichever grant is ruled must be made on both in the same session, and on
Boston. The outside-in proof, as the org-wide API key:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H "X-Api-Key: $ESPO_API_KEY" \
  'https://<crm>/api/v1/CEvent/<id>/partnerProfiles?maxSize=1'   # 200
```

and as a real Marketing Admin member in a browser, once Phase B is on
crm-test: open an event, and the Partners picker lists the partner profiles.
**An administrator's test proves nothing here.**

## 8. Then production

At the Sunday 17:00 UTC slot, by a human, from inside the deployed web
container, after crm-test has been reviewed. Order: § 2 dry run → § 2 apply
(with `--carry-host`) → § 5 by hand → § 6. Production's events carry no
partner host as far as is known, so after the change nothing visible differs
until Phase B ships and a partner is picked.

## 9. Then Boston

With the release that carries the Phase B code, the same three steps from
inside Boston's web container. The relation table name is in the plan, so
Boston's schema matches Cleveland's exactly — which the chapter network's
conformance check will otherwise report as drift.

---

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.1 | 10-07-26 03:45 | Claude (Claude Code) | Applied § 2, § 4 and § 7 to crm-test and verified as the org-wide API key; § 5 owed to Doug. Role grant ruled read-all. |
| 1.0 | 10-07-26 03:40 | Claude (Claude Code) | First version. State read from crm-test; both appliers dry-run clean; nothing applied yet. Records the Marketing Admin Role gap (§ 7). |
