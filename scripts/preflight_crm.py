"""Read-only production-readiness pre-flight for an EspoCRM instance.

Before pointing the app at a *new* CRM (e.g. production), verify it actually has
the schema the orchestrators + submission log write to — the crm-test drift saga
(see CLAUDE.md / CHANGELOG.md) showed how a missing entity / field / enum option
silently sinks a live submission. This audits all three, read-only.

It does NOT (cannot, read-only) verify the API user's *create grants* — those are
proven by the controlled labelled test submissions at go-live (DEPLOYMENT.md
"Verify a live deployment"). Enum coverage is advisory: orchestrators now DROP an
unrecognized enum value (v0.6.0+), so a missing option degrades data rather than
failing the create — but it's still reported so you know what won't store.

Usage:
    uv run python scripts/preflight_crm.py \
        --url https://crm.clevelandbusinessmentors.org --key <API_KEY>
    # or via env: PREFLIGHT_CRM_URL / PREFLIGHT_CRM_KEY

Exit code is non-zero if any CRITICAL check fails (missing entity or field).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

# Run-as-a-script: put the repo root (this file's parent's parent) on the path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.espo import EspoClient, EspoError  # noqa: E402
from core.schema_contract import EXPECTED_ENUMS  # noqa: E402

# --- Entities the app creates/links (every one must exist) -------------------
REQUIRED_ENTITIES = [
    "Account", "Contact", "CClientProfile", "CEngagement", "CMentorProfile",
    "CPartnerProfile", "CSponsorProfile", "CInformationRequest", "CIntakeSubmission",
]

# --- Fields each orchestrator / the submission log writes (must exist) -------
# Sourced from forms/*/orchestrator.py + core/submission_log.py. Link FKs are the
# "<link>Id" attributes the creates set.
REQUIRED_FIELDS: dict[str, list[str]] = {
    "Account": [
        "name", "cAccountType", "cCompanyType", "cBusinessStage",
        "cIndustrySector", "cClientStatus", "website",
    ],
    "Contact": [
        "firstName", "lastName", "emailAddress", "phoneNumber", "addressPostalCode",
        "addressStreet", "accountId", "cContactType", "middleName",
        "cPreferredName", "cLinkedInProfile", "description",
    ],
    "CClientProfile": ["name", "clientcontactId", "linkedCompanyId"],
    "CEngagement": [
        "name", "engagementStatus", "mentoringFocusAreas", "mentoringNeedsDescription",
        "engagementClientId", "primaryEngagementContactId", "description",
        # staff tools (assignments). The assignment tool writes BOTH assignedUser
        # and assignedUsers (the app adapts per instance), so either one suffices —
        # not listed here as a hard requirement.
        "mentorProfileId", "requestedMentorId",
    ],
    "CMentorProfile": [
        "name", "contactRecordId", "mentorStatus", "mentorType", "mentoringWhyInterested",
        "mentorProfessionalBio", "mentoringFocusAreas", "fluentLanguages", "industrySector",
        "howDidYouHearAboutCBM", "felonyConfiction", "termsAccepted", "description",
        "resumeUpload", "resumeUploadId",
        # staff tools (assignments/mentoradmin):
        "acceptingNewClients", "availableCapacity", "assignedUserId", "cbmEmail",
        "recordStatus",
    ],
    "CPartnerProfile": [
        "name", "partnerCompanyId", "primaryPartnercontactId", "partnershipStatus",
        "partnershipType", "partnershipValue", "description",
    ],
    "CSponsorProfile": ["name", "sponsorCompanyId", "sponsorContactId", "description"],
    "CInformationRequest": [
        "name", "email", "submitterEmail", "form", "message", "description",
        "requestStatus", "contactId", "phone", "company", "source", "infoRequestCompanyId",
    ],
    "CIntakeSubmission": [
        "form", "reason", "status", "source", "submitterEmail", "description", "contactId",
    ],
}


async def _safe_metadata(client: EspoClient, key: str):
    """Fetch a metadata key, treating any error or empty/non-JSON body (EspoCRM
    returns an empty 200 for a path the API user can't see) as 'not available'."""
    try:
        return await client.metadata(key)
    except Exception:  # noqa: BLE001 — EspoError, JSON decode (empty 200), transport
        return None


async def run(url: str, key: str) -> int:
    client = EspoClient(url, key, 30)
    critical = 0
    advisory = 0
    print(f"Pre-flight against {url}\n" + "=" * 64)

    # 1. Entities + fields. A required name is present if it's a field, a link, or
    #    a link FK attribute (``<link>Id`` / hasMany ``<link>Ids``) — link FKs live
    #    under .links, not .fields.
    print("\n[entities + fields]")
    visible = 0
    for entity in REQUIRED_ENTITIES:
        defs = await _safe_metadata(client, f"entityDefs.{entity}.fields")
        if not isinstance(defs, dict) or not defs:
            print(f"  ✗ {entity}: not visible (entity absent, or the API user has "
                  f"no grant on this scope)")
            critical += 1
            continue
        visible += 1
        links = await _safe_metadata(client, f"entityDefs.{entity}.links")
        names = set(defs) | set(links or {})

        def present(name: str) -> bool:
            if name in names:
                return True
            for suffix in ("Ids", "Id"):
                if name.endswith(suffix) and name[: -len(suffix)] in names:
                    return True
            return False

        required = REQUIRED_FIELDS.get(entity, [])
        missing = [f for f in required if not present(f)]
        if missing:
            print(f"  ✗ {entity}: missing fields/links: {', '.join(missing)}")
            critical += len(missing)
        else:
            print(f"  ✓ {entity}: all {len(required)} required fields/links present")

    # 2. Enum option coverage (advisory — orchestrators drop unknown values)
    print("\n[enum option coverage]  (advisory: unknown values are dropped, not fatal)")
    for (entity, field), expected in EXPECTED_ENUMS.items():
        try:
            options = await client.metadata_enum_options(entity, field)
        except Exception:  # noqa: BLE001 — empty 200 / transport, like _safe_metadata
            options = None
        if options is None:
            print(f"  ? {entity}.{field}: no options found (field missing or not an enum)")
            advisory += 1
            continue
        missing = [v for v in expected if v not in options]
        if missing:
            print(f"  ! {entity}.{field}: missing {len(missing)} value(s): {missing}")
            advisory += len(missing)
        else:
            print(f"  ✓ {entity}.{field}: all {len(expected)} expected values present")

    # Summary
    print("\n" + "=" * 64)
    print(f"CRITICAL issues (missing entity/field): {critical}")
    print(f"Advisory issues (enum values that won't store): {advisory}")
    if visible == 0:
        print("\nRESULT: NOT READY — the API user can't see ANY of the app's scopes."
              "\n  This key has no role/grants (record reads 403, scopes empty), so it's"
              "\n  either unprovisioned or the custom entities don't exist yet. Re-run with"
              "\n  an ADMIN key to confirm which, then grant create on every entity above"
              "\n  to the intake API user (+ edit on Contact for info-request append).")
    elif critical:
        print("\nRESULT: NOT READY — resolve the missing entities/fields in the CRM first.")
    else:
        print("\nRESULT: schema looks ready. Next: deploy dry-run, then a labelled test "
              "submission per form to prove create-grants (read-only can't check grants).")
    return 1 if critical else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only EspoCRM production pre-flight.")
    ap.add_argument("--url", default=os.environ.get("PREFLIGHT_CRM_URL"))
    ap.add_argument("--key", default=os.environ.get("PREFLIGHT_CRM_KEY"))
    args = ap.parse_args()
    if not args.url or not args.key:
        ap.error("provide --url and --key (or PREFLIGHT_CRM_URL / PREFLIGHT_CRM_KEY)")
    return asyncio.run(run(args.url.rstrip("/"), args.key))


if __name__ == "__main__":
    sys.exit(main())
