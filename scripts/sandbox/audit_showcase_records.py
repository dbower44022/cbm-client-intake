"""Report every empty field and every empty relationship on the showcase records.

Doug's standard (2026-08-22): a showcase record should have **data in every
field, and at least one record on every relationship**. A demo that opens a tab
and finds it blank teaches the trainee that the feature is broken.

This is the check for that. It reads the CRM's own ``entityDefs`` rather than a
hand-kept list, so a field the CRM team adds tomorrow shows up here as a new gap
instead of being silently missed.

What it deliberately ignores:

* system bookkeeping — ``createdAt/By``, ``modifiedAt/By``, ``streamUpdatedAt``;
* ``foreign`` fields, which are read-only mirrors of a linked record's value
  and cannot be filled here ([[espo-foreign-fields-are-readonly-mirrors]]);
* ``currencyConverted`` and ``autoincrement``, which the CRM computes;
* link fields, which are reported under relationships instead of twice.

Read-only. Run it after seeding and after any CRM field change.

    uv run python scripts/sandbox/audit_showcase_records.py
    uv run python scripts/sandbox/audit_showcase_records.py --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.espo import EspoClient, EspoError  # noqa: E402
from core.config import get_settings  # noqa: E402

#: (entity, record name, why it is a showcase record)
SHOWCASE: tuple[tuple[str, str, str], ...] = (
    ("CMentorProfile", "Joe Mentor", "the mentor a trainee signs in as"),
    ("Contact", "Joe Mentor", "that mentor's own Contact"),
    ("CEngagement", "Brightline Bakehouse — Mentoring", "the mentor's showcase client"),
    ("CClientProfile", "Brightline Bakehouse — Client Profile", "its client profile"),
    ("Account", "Brightline Bakehouse", "its company"),
    ("Contact", "Dana Whitcomb", "its client contact"),
    ("CPartnerProfile", "Cuyahoga Small Business Alliance", "the partner showcase"),
    ("CSponsorProfile", "Harrowgate Family Trust", "the funder showcase"),
)

SKIP_TYPES = {"foreign", "currencyConverted", "autoincrement", "linkMultiple",
              "link", "linkParent", "linkOne", "image", "file", "attachmentMultiple"}

#: Blanks that are CORRECT for the record's role. Filling these would make the
#: data worse, not better — an Active mentor with a departureReason, or a client
#: company carrying sponsorship fields. Each entry says why.
EXPECTED_EMPTY: dict[tuple[str, str], set[str]] = {}


def _expect(entity: str, name: str, *fields: str) -> None:
    EXPECTED_EMPTY.setdefault((entity, name), set()).update(fields)


# EspoCRM stock features CBM does not use, on every Contact and Account.
_STOCK = ("campaign", "portalUser", "portalUsers", "originalLead", "opportunityRole",
          "acceptanceStatus", "acceptanceStatusCalls", "acceptanceStatusMeetings")
# Composite address fields are assembled from their sub-fields and always read
# empty as a single attribute ([[espo-layout-api-readable]] neighbours).
_COMPOSITE = ("address", "billingAddress", "shippingAddress")
# Derived from the account-contact relationship; notStorable, cannot be written.
_DERIVED = ("accountRole", "accountAnyId", "accountIsInactive", "contactRole",
            "contactIsInactive", "title")

for _who in (("Contact", "Joe Mentor"), ("Contact", "Dana Whitcomb")):
    _expect(*_who, *_STOCK, *_COMPOSITE, *_DERIVED, "cSuffix",
            # No intake submissions exist in the sandbox yet.
            "cIntakeSubmissions", "cInformationRequests",
            # Neither contact is a partner or funder contact.
            "cPartnerProfile", "cPartnerProfiles", "cSponsorProfile",
            "cSponsorProfiles", "cContributions", "cLiaisonForPartnerAccounts",
            "cPresenterEvents", "cAssignedUser")
# Joe is retired, so no employer — and title/accountRole derive from that link.
_expect("Contact", "Joe Mentor", "account", "accounts", "cPrimaryCompany",
        # He is the mentor on the engagement, never the client contact.
        "cClientContact", "cEngagementsAsContact", "cPrimaryEngagementsAsContact")
_expect("Contact", "Dana Whitcomb", "cMentorProfile", "cSpouseName", "middleName")

# Wrong for an ACTIVE mentor: these belong to declined, paused or departed ones.
_expect("CMentorProfile", "Joe Mentor",
        "declinedReason", "rejectionReason", "departureDate", "departureReason",
        "mentorPauseStartDate", "mentorPauseEndDate")

_expect("CEngagement", "Brightline Bakehouse — Mentoring",
        # Active and not on hold.
        "closeReason", "holdEndDate",
        # The app DELIBERATELY discards the stored value and derives the next
        # session from real sessions; a value here is the ghost-session bug.
        "nextSessionDateTime",
        # Written by the Drive integration, which the sandbox cannot use yet.
        "documentsFolderUrl")

_expect("Account", "Brightline Bakehouse", *_STOCK, *_COMPOSITE, *_DERIVED,
        # Partner and funder fields on a CLIENT company.
        "cPartnerNotes", "cPartnerOrganizationType", "cSponsorNotes",
        "cSponsorshipLevel", "cSponsorshipStartDate", "cSponsorshipRenewalDate",
        "cAnnualPledgeAmount", "cAnnualPledgeAmountCurrency", "cPartnerProfile",
        "cCompanyPartnerProfiles", "cSponsorProfiles", "cContributions",
        "cAssignedLiaison", "cInformationRequests",
        # Single-site business: no parent and no subsidiaries.
        "cParentAccount", "cChildAccounts")
SKIP_FIELDS = {"createdAt", "createdBy", "modifiedAt", "modifiedBy", "deleted",
               "streamUpdatedAt", "teams", "assignedUser", "assignedUsers",
               "collaborators"}


def is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return not value
    return False


async def audit(client: EspoClient, entity: str, name: str, defs: dict, verbose: bool):
    found = await client.list(
        entity, select="id,name", max_size=1,
        where=[{"type": "equals", "attribute": "name", "value": name}],
    )
    rows = found.get("list", [])
    if not rows:
        print(f"\n### {entity} / {name}\n    !! NOT FOUND")
        return (0, 0, 0, 0)
    record_id = rows[0]["id"]

    fields = (defs.get(entity) or {}).get("fields") or {}
    links = (defs.get(entity) or {}).get("links") or {}

    checkable = [
        key for key, spec in fields.items()
        if key not in SKIP_FIELDS
        and spec.get("type") not in SKIP_TYPES
        and not spec.get("disabled")
        and not spec.get("readOnly")
        # notStorable fields mirror something else (Contact.title is the
        # account-contact role) and cannot be written at all.
        and not spec.get("notStorable")
        and not spec.get("directUpdateDisabled")
    ]
    expected = EXPECTED_EMPTY.get((entity, name), set())
    record = await client.get(entity, record_id, select=",".join(checkable + ["id"]))
    # Drop the deliberate blanks from the DENOMINATOR too — counting them as
    # filled would flatter the score instead of measuring it.
    checkable = [k for k in checkable if k not in expected]
    empty = sorted(k for k in checkable if is_empty(record.get(k)))
    filled = len(checkable) - len(empty)

    # Relationships: hasMany needs at least one related record; belongsTo needs a value.
    empty_links: list[str] = []
    total_links = 0
    for key, spec in links.items():
        kind = spec.get("type")
        if key in SKIP_FIELDS or spec.get("disabled") or key in expected:
            continue
        if kind in ("hasMany", "hasChildren"):
            total_links += 1
            try:
                related = await client.list_related(entity, record_id, key, max_size=1)
                if not int(related.get("total") or 0):
                    empty_links.append(f"{key} ({spec.get('entity') or '?'})")
            except EspoError:
                pass  # not readable by this key — not a data gap
        elif kind in ("belongsTo", "hasOne"):
            total_links += 1
            if is_empty(record.get(f"{key}Id")):
                empty_links.append(f"{key} ({spec.get('entity') or '?'})")

    print(f"\n### {entity} / {name}")
    print(f"    fields {filled}/{len(checkable)} filled, "
          f"relationships {total_links - len(empty_links)}/{total_links} populated")
    if empty:
        print(f"    empty fields ({len(empty)}): {', '.join(empty)}")
    if empty_links:
        print(f"    empty relationships ({len(empty_links)}): {', '.join(empty_links)}")
    if verbose and not empty and not empty_links:
        print("    complete")
    return (filled, len(checkable), total_links - len(empty_links), total_links)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    base = settings.espo_base_url or ""
    if "crm-test" not in base.lower():
        print(f"REFUSING: ESPO_BASE_URL is {base!r}, not the crm-test sandbox.")
        return 2

    client = EspoClient(base, settings.espo_api_key, settings.request_timeout_seconds)
    defs = await client.metadata("entityDefs")

    print(f"Showcase-record coverage on {base}")
    totals = [0, 0, 0, 0]
    for entity, name, _why in SHOWCASE:
        result = await audit(client, entity, name, defs, args.verbose)
        totals = [a + b for a, b in zip(totals, result)]
    print(f"\nTOTAL fields {totals[0]}/{totals[1]}, "
          f"relationships {totals[2]}/{totals[3]}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
