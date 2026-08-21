"""Read-only conformance check for an EspoCRM instance.

**What it is.** The check half of *Phase 1* in
``prds/multi-chapter-deployment-plan.md``: "is this instance equal to what the
application requires, and if not, exactly how does it differ". It began as a
production-readiness pre-flight (before pointing the app at a new CRM, verify it
has the schema the orchestrators write to — the crm-test drift saga showed how a
missing entity / field / enum option silently sinks a live submission) and it is
now also the thing a deploy gate runs, so it answers to the interface contract in
that phase:

* **C1 headless** — arguments and environment only, no prompt, no human decision.
* **C2 least credential** — the org-wide **API key** and nothing else. Checking
  never needs an Admin-type account; only *applying* does, and this script does
  not apply.
* **C3 a credential problem must never read as a configuration problem.**
  EspoCRM returns an **empty 200** for a metadata scope the caller cannot see, so
  "absent" and "forbidden" look identical at the transport layer. This script
  disambiguates them against the caller's own ACL table (``App/user``) and
  reports — and exit-codes — them separately. The previous version of this file
  printed both as one line reading "entity absent, or the API user has no grant".
* **C4 exit codes with defined meanings** (see below).
* **C5 a machine-readable result on every exit code**, via ``--json``.

It does NOT (cannot, read-only) verify the API user's *create grants* — those are
proven by the controlled labelled test submissions at go-live (DEPLOYMENT.md
"Verify a live deployment").

Usage::

    uv run python scripts/preflight_crm.py \
        --url https://crm.clevelandbusinessmentors.org --key <API_KEY>
    # or via env: PREFLIGHT_CRM_URL / PREFLIGHT_CRM_KEY
    # machine-readable, for a gate or the fleet console:
    uv run python scripts/preflight_crm.py --json

Exit codes (the contract's C4; 2 and 4 are reserved for an applier and cannot
arise here)::

    0  conformant — nothing required is missing
    1  drift      — something required is missing, and we could see that it is
    3  unchecked  — something could not be checked at all (403 on a scope, a
                    transport failure, an unexpected error). Conformance is
                    UNKNOWN, which is not the same as bad.

**1 takes precedence over 3**: a certain problem is more actionable than an
uncertain one, and both mean "do not proceed". Enum-option gaps stay **advisory**
and do not change the exit code (orchestrators drop an unrecognized value rather
than failing the create) unless ``--strict-enums`` is passed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field as dc_field
from typing import Any, Optional

# Run-as-a-script: put the repo root (this file's parent's parent) on the path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import Settings, get_settings  # noqa: E402
from core.espo import EspoClient, EspoError, EspoTransportError, is_forbidden  # noqa: E402
from core.schema_contract import EXPECTED_ENUMS  # noqa: E402

# --- Entities the app creates/links (every one must exist) -------------------
REQUIRED_ENTITIES = [
    "Account", "Contact", "CClientProfile", "CEngagement", "CMentorProfile",
    "CPartnerProfile", "CSponsorProfile", "CInformationRequest", "CIntakeSubmission",
]

# --- Fields each orchestrator / the receipt engine writes (must exist) -------
# Sourced from forms/*/orchestrator.py + core/receipts.py. Link FKs are the
# "<link>Id" attributes the creates set.
#
# Corrected 2026-08-21, by running this check against crm-test: the list had
# been carrying three requirements no code has written for months —
# ``Account.cAccountType`` (removed from BOTH CRMs; every orchestrator's
# docstring says so) and ``CIntakeSubmission.reason`` / ``.status`` (superseded
# by the ``intakeStatus`` vocabulary when the receipt engine replaced
# ``core/submission_log.py``, which no longer exists). A conformance check that
# demands dead fields reports drift that cannot be fixed, which is how a gate
# gets ignored.
REQUIRED_FIELDS: dict[str, list[str]] = {
    "Account": [
        "name", "cCompanyType", "cBusinessStage",
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
    # core/receipts.py: set at create, plus the keys the engine owns on sync.
    "CIntakeSubmission": [
        "name", "form", "submitterEmail", "source", "intakeStatus", "intakeMessage",
        "payload", "emailLink", "contactId",
        "dispositionedBy", "dispositionedAt", "dispositionReason",
    ],
}

# --- Email templates the code renders by NAME -------------------------------
# The app looks these up by name, so a missing one is a feature that silently
# does nothing. Sources: assignments/frontend/app.js (the assignment notice) and
# events/notify.py (the five follow-up kinds). Kept in sync by
# tests/test_preflight_contract.py.
REQUIRED_EMAIL_TEMPLATES = [
    "MentorAssignmentNotice",
    "EventReminder",
    "EventRecordingAvailable",
    "EventNoShow",
    "EventMentorCTA",
    "EventSurvey",
]

# Outcomes. ``ABSENT`` is drift we could see; ``FORBIDDEN`` / ``UNREACHABLE`` /
# ``ERROR`` are all "we could not look", which is C3's whole point.
OK, ABSENT, FORBIDDEN, UNREACHABLE, ERROR, ADVISORY = (
    "conformant", "absent", "forbidden", "unreachable", "error", "advisory",
)
_UNCHECKED = {FORBIDDEN, UNREACHABLE, ERROR}


@dataclass
class Check:
    category: str
    target: str
    outcome: str
    detail: str = ""
    missing: list[str] = dc_field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        d = {"category": self.category, "target": self.target, "outcome": self.outcome}
        if self.detail:
            d["detail"] = self.detail
        if self.missing:
            d["missing"] = self.missing
        return d


def required_teams(settings: Settings) -> list[str]:
    """Every team name the product gates on, read from the settings themselves.

    Derived rather than hard-coded so a new gate cannot be forgotten here: any
    ``*_allowed_teams_list`` property plus ``mentor_team_name`` (which mentor
    provisioning places new users into).
    """
    names: set[str] = set()
    for attr in dir(type(settings)):
        if attr.endswith("_allowed_teams_list"):
            names.update(getattr(settings, attr) or [])
    if settings.mentor_team_name:
        names.add(settings.mentor_team_name)
    return sorted(names)


class Probe:
    """Every remote read goes through here so a 403, a transport failure and a
    real answer can never be confused for one another (C3)."""

    def __init__(self, client: EspoClient) -> None:
        self.c = client
        self.acl: dict[str, Any] = {}

    async def load_acl(self) -> tuple[str, str]:
        """The caller's own ACL table, used to tell 'absent' from 'forbidden'."""
        try:
            user = await self.c.app_user()
        except EspoTransportError as exc:
            return UNREACHABLE, str(exc)
        except EspoError as exc:
            return (FORBIDDEN if is_forbidden(exc) else ERROR), str(exc)
        except Exception as exc:  # noqa: BLE001 — empty/non-JSON body
            return ERROR, f"{type(exc).__name__}: {exc}"
        self.acl = ((user.get("acl") or {}).get("table") or {})
        return OK, ""

    def readable(self, entity: str) -> Optional[bool]:
        """True/False when the ACL table says, None when we have no table
        (an admin key reports none, and then we cannot disambiguate)."""
        if not self.acl:
            return None
        row = self.acl.get(entity)
        if row is None:
            return False
        if isinstance(row, str):  # some scopes report a bare level
            return row not in ("no", "false")
        return row.get("read") not in (None, "no", False)

    async def call(self, coro) -> tuple[str, Any, str]:
        try:
            return OK, await coro, ""
        except EspoTransportError as exc:
            return UNREACHABLE, None, str(exc)
        except EspoError as exc:
            return (FORBIDDEN if is_forbidden(exc) else ERROR), None, str(exc)
        except Exception as exc:  # noqa: BLE001 — empty 200 => JSON decode
            return ERROR, None, f"{type(exc).__name__}: {exc}"

    async def metadata(self, key: str, entity: str) -> tuple[str, Any, str]:
        """Metadata, with EspoCRM's empty-200-for-an-invisible-scope resolved
        against the ACL table instead of being reported as 'absent'."""
        status, value, detail = await self.call(self.c.metadata(key))
        if status != OK:
            return status, None, detail
        if isinstance(value, dict) and value:
            return OK, value, ""
        readable = self.readable(entity)
        if readable is False:
            return FORBIDDEN, None, (
                f"the API user has no read grant on {entity}, so its metadata "
                f"comes back empty — this says nothing about whether it exists"
            )
        if readable is None:
            return ERROR, None, (
                f"{entity} metadata is empty and no ACL table was available to "
                f"tell 'absent' from 'forbidden'"
            )
        return ABSENT, None, f"{entity} is readable to this user but has no field definitions"

    async def list_names(self, entity: str, page: int = 200, cap: int = 2000):
        """All record names for a small reference entity (Team, EmailTemplate).

        Paged at ``page`` because a maxSize above EspoCRM's
        ``recordListMaxSizeLimit`` (200) is a **403, not a truncation**
        ([[espo-list-maxsize-403]]).
        """
        names: list[str] = []
        offset = 0
        while offset < cap:
            status, envelope, detail = await self.call(
                self.c.list(entity, max_size=page, offset=offset, select="name")
            )
            if status != OK:
                return status, None, detail
            rows = envelope.get("list") or []
            names.extend(str(r.get("name") or "") for r in rows)
            if len(rows) < page:
                break
            offset += page
        return OK, names, ""


async def run(url: str, key: str, *, strict_enums: bool = False) -> tuple[int, dict]:
    settings = get_settings()
    client = EspoClient(url, key, 30)
    probe = Probe(client)
    checks: list[Check] = []

    acl_status, acl_detail = await probe.load_acl()
    if acl_status != OK:
        checks.append(Check("access", "App/user", acl_status, acl_detail))

    # 1. Entities + fields. A required name is present if it's a field, a link, or
    #    a link FK attribute (``<link>Id`` / hasMany ``<link>Ids``) — link FKs live
    #    under .links, not .fields.
    for entity in REQUIRED_ENTITIES:
        status, defs, detail = await probe.metadata(f"entityDefs.{entity}.fields", entity)
        if status != OK:
            checks.append(Check("entity", entity, status, detail))
            continue
        link_status, links, link_detail = await probe.metadata(
            f"entityDefs.{entity}.links", entity
        )
        names = set(defs) | set(links or {} if link_status == OK else {})

        def present(name: str) -> bool:
            if name in names:
                return True
            for suffix in ("Ids", "Id"):
                if name.endswith(suffix) and name[: -len(suffix)] in names:
                    return True
            return False

        required = REQUIRED_FIELDS.get(entity, [])
        missing = [f for f in required if not present(f)]
        checks.append(Check(
            "entity", entity, ABSENT if missing else OK,
            f"missing {len(missing)} of {len(required)} required fields/links"
            if missing else f"all {len(required)} required fields/links present",
            missing,
        ))

    # 2. Enum option coverage — advisory by default (orchestrators drop unknown
    #    values, so a missing option degrades data rather than failing a create).
    for (entity, fieldname) in EXPECTED_ENUMS:
        expected = EXPECTED_ENUMS[(entity, fieldname)]
        status, options, detail = await probe.call(
            client.metadata_enum_options(entity, fieldname)
        )
        target = f"{entity}.{fieldname}"
        if status != OK:
            checks.append(Check("enum", target, status, detail))
            continue
        if options is None:
            checks.append(Check("enum", target, ADVISORY, "no options found (field missing or not an enum)"))
            continue
        missing = [v for v in expected if v not in options]
        checks.append(Check(
            "enum", target, (ABSENT if strict_enums else ADVISORY) if missing else OK,
            f"{len(missing)} of {len(expected)} expected values missing" if missing
            else f"all {len(expected)} expected values present",
            missing,
        ))

    # 3. Teams the product gates on. A missing team is a locked-out application.
    wanted_teams = required_teams(settings)
    status, live, detail = await probe.list_names("Team")
    if status != OK:
        checks.append(Check("team", "Team", status, detail))
    else:
        missing = [t for t in wanted_teams if t not in live]
        checks.append(Check(
            "team", "Team", ABSENT if missing else OK,
            f"{len(live)} teams on the instance; {len(wanted_teams)} required",
            missing,
        ))

    # 4. Email templates the code renders by name.
    status, live, detail = await probe.list_names("EmailTemplate")
    if status != OK:
        checks.append(Check("emailTemplate", "EmailTemplate", status, detail))
    else:
        missing = [t for t in REQUIRED_EMAIL_TEMPLATES if t not in live]
        checks.append(Check(
            "emailTemplate", "EmailTemplate", ABSENT if missing else OK,
            f"{len(live)} templates on the instance; "
            f"{len(REQUIRED_EMAIL_TEMPLATES)} required",
            missing,
        ))

    counts: dict[str, int] = {}
    for c in checks:
        counts[c.outcome] = counts.get(c.outcome, 0) + 1
    drift = counts.get(ABSENT, 0)
    unchecked = sum(counts.get(k, 0) for k in _UNCHECKED)
    # 1 beats 3: a certain problem is more actionable than an uncertain one.
    code = 1 if drift else (3 if unchecked else 0)
    result = {
        "instance": url,
        "standardVersion": None,  # Stamp B — nothing writes it yet (plan, Phase 1)
        "mode": "check",
        "strictEnums": strict_enums,
        "exitCode": code,
        "counts": counts,
        "checks": [c.as_dict() for c in checks],
    }
    return code, result


_MARK = {OK: "✓", ABSENT: "✗", ADVISORY: "!", FORBIDDEN: "⊘", UNREACHABLE: "…", ERROR: "?"}


def render(result: dict) -> None:
    print(f"Conformance check against {result['instance']}\n" + "=" * 64)
    last = None
    for c in result["checks"]:
        if c["category"] != last:
            print(f"\n[{c['category']}]")
            last = c["category"]
        line = f"  {_MARK.get(c['outcome'], '·')} {c['target']}: {c.get('detail', c['outcome'])}"
        print(line)
        if c.get("missing"):
            print(f"      missing: {', '.join(c['missing'])}")
    counts = result["counts"]
    print("\n" + "=" * 64)
    print("  ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "no checks ran")
    code = result["exitCode"]
    if code == 0:
        print("\nRESULT: CONFORMANT. (Read-only: create grants are proven by a "
              "labelled test submission per form, not by this check.)")
    elif code == 1:
        print("\nRESULT: DRIFT — something required is missing. Resolve it in the CRM.")
    else:
        print("\nRESULT: UNCHECKED — one or more checks could not run at all, so "
              "conformance is unknown.\n  A ⊘ is a missing grant on THIS key, not "
              "a missing entity. A … is the CRM being unreachable.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only EspoCRM conformance check.")
    ap.add_argument("--url", default=os.environ.get("PREFLIGHT_CRM_URL"))
    ap.add_argument("--key", default=os.environ.get("PREFLIGHT_CRM_KEY"))
    ap.add_argument("--json", action="store_true",
                    help="emit the machine-readable result instead of the report")
    ap.add_argument("--strict-enums", action="store_true",
                    help="treat a missing enum option as drift rather than advisory")
    args = ap.parse_args()
    if not args.url or not args.key:
        # Fall back to the deployment's own configured CRM, which is what makes
        # this runnable inside a container with no arguments (C1).
        s = get_settings()
        args.url = args.url or s.espo_base_url
        args.key = args.key or s.espo_api_key
    if not args.url or not args.key:
        ap.error("provide --url and --key (or PREFLIGHT_CRM_URL / PREFLIGHT_CRM_KEY, "
                 "or ESPO_BASE_URL / ESPO_API_KEY)")
    code, result = asyncio.run(
        run(args.url.rstrip("/"), args.key, strict_enums=args.strict_enums)
    )
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        render(result)
    return code


if __name__ == "__main__":
    sys.exit(main())
