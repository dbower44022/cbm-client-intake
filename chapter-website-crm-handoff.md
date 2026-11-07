# The chapter website's CRM change

**Document:** CRM change for the chapter website, pieces D and E of `prds/chapter-website-plan.md`
**Version:** 1.0
**Status:** Applied on crm-test 11-07-26; production and Boston owed
**Owner:** Doug Bower
**Last Updated:** 11-07-26 15:05

---

## What it is

Three additions, all additive. Nothing existing is renamed, removed or changed.

1. A field on the lead entity: `CProspect.buttonPlacement`, a varchar of 64 characters, labelled **Website button**. The public forms write which button on the chapter website brought the person (plan decision 4.4). It must never be made Read-only: a Read-only field silently drops every write from the application.
2. A lead source option: `CProspect.leadSource` gains **Newsletter signup** (Association ruling 43).
3. A receipt form option: `CIntakeSubmission.form` gains **Newsletter**.

The whole change is the plan file `crm-plans/chapter-website.json`. It is applied through the API by `apply_crm_plan.py`, never by hand in Entity Manager.

## Applied

- **crm-test:** applied and read back 11-07-26 19:55 UTC (plan fingerprint `9e1fbf56fa32`). The application's own key reads `CProspect` with the new field (HTTP 200).
- **Production:** owed, at a Sunday 17:00 UTC slot, run from inside the production web container. Tracked in `OPEN-ITEMS.md` #72.
- **Boston:** owed with the next chapter release.

## The application without it

Every part feature-detects. On a CRM without the field the button placement is simply not recorded; without the two options the CRM's enum check drops the value, and the lead or receipt is still written.

---

## Change log

| Version | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 11-07-26 15:05 | Claude (Claude Code) | First version; applied on crm-test. |
