"""Label the campaign entity and its links "Outreach Campaign" in the CRM (ruling 35).

EspoCRM ships its own ``Campaign`` entity and a native ``campaign`` link on
Contact and Account, both labelled "Campaign". The Phase 1 handoff labelled
our entity and its links "Campaign" too, so every Contact and Company showed
two fields with one name — in the detail view, the list column picker, the
filters, export, mass update and the report builder. Doug's ruling 35
(10-17-26): **a custom field never takes a built-in field's name**; ours is
renamed "Outreach Campaign" in the CRM. The application's own screens keep the
word "Campaign" (CM-11) — the application has no native field to collide with.

**What it changes**, through EspoCRM's Label Manager, language ``en_US``:

* the entity: ``scopeNames`` / ``scopeNamesPlural`` of ``COutreachCampaign``;
* the link and its field label on the eight records that carry it — Contact
  and Account (``cOutreachCampaign``), CEngagement, CInformationRequest,
  CEventRegistration, CPartnerProfile, CSponsorProfile and COutreachTouch
  (``outreachCampaign``).

Labels only. No stored name changes, no data changes, no application code
depends on a label. Idempotent; **dry-run by default**; needs an Admin-type
login (the org-wide key is refused on Label Manager), run through
``scripts/run_with_admin.py``::

    PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/relabel_outreach_campaign.py
    PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/relabel_outreach_campaign.py --apply

Another CRM: ``run_with_admin.py --env <file>`` (production, Boston).
Undo: run with ``--label Campaign --plural Campaigns --apply``.

Exit codes: 0 done, 1 a write failed, 2 no credential, 3 unreachable.
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
from typing import Any

import httpx

ENTITY = "COutreachCampaign"
#: (scope, link/field name) — every place the link to the campaign is labelled.
LINKS: tuple[tuple[str, str], ...] = (
    ("Contact", "cOutreachCampaign"),
    ("Account", "cOutreachCampaign"),
    ("CEngagement", "outreachCampaign"),
    ("CInformationRequest", "outreachCampaign"),
    ("CEventRegistration", "outreachCampaign"),
    ("CPartnerProfile", "outreachCampaign"),
    ("CSponsorProfile", "outreachCampaign"),
    ("COutreachTouch", "outreachCampaign"),
)
LANGUAGE = "en_US"


class Admin:
    def __init__(self, base: str, user: str, password: str) -> None:
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.api = base.rstrip("/") + "/api/v1"
        self.http = httpx.Client(timeout=30, headers={"Espo-Authorization": token})

    def post(self, path: str, body: dict[str, Any]) -> Any:
        r = self.http.post(f"{self.api}/{path}", json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"POST {path} -> {r.status_code} {r.text[:200]}")
        return r.json() if r.content else None

    def scope_data(self, scope: str) -> dict[str, Any]:
        return self.post("LabelManager/action/getScopeData", {"scope": scope, "language": LANGUAGE}) or {}


def wanted(label: str, plural: str) -> dict[str, dict[str, str]]:
    """{scope: {"category[.]key": label}} for every label this script owns."""
    out: dict[str, dict[str, str]] = {
        "Global": {f"scopeNames[.]{ENTITY}": label, f"scopeNamesPlural[.]{ENTITY}": plural},
    }
    for scope, name in LINKS:
        out.setdefault(scope, {}).update({f"links[.]{name}": label, f"fields[.]{name}": label})
    return out


def current(data: dict[str, Any], key: str) -> Any:
    """The stored label. Label Manager keys each category's entries by the
    FULL ``category[.]name`` key (read on crm-test 10-17-26)."""
    category = key.partition("[.]")[0]
    return (data.get(category) or {}).get(key)


def main() -> int:
    ap = argparse.ArgumentParser(description="Label the campaign entity and its links 'Outreach Campaign' (ruling 35).")
    ap.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    ap.add_argument("--label", default="Outreach Campaign")
    ap.add_argument("--plural", default="Outreach Campaigns")
    args = ap.parse_args()
    base = os.environ.get("ESPO_ADMIN_BASE") or os.environ.get("ADMIN_BASE")
    user = os.environ.get("ESPO_ADMIN_USER") or os.environ.get("ADMIN_USER")
    password = os.environ.get("ESPO_ADMIN_PASS") or os.environ.get("ADMIN_PASS")
    if not (base and user and password):
        print("No admin credential — run through scripts/run_with_admin.py.", file=sys.stderr)
        return 2
    print(f"CRM:  {base}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN - nothing will change'}\n")
    admin = Admin(base, user, password)
    failed = changed = 0
    try:
        for scope, labels in wanted(args.label, args.plural).items():
            data = admin.scope_data(scope)
            todo = {k: v for k, v in labels.items() if current(data, k) != v}
            for k, v in labels.items():
                mark = "->" if k in todo else "ok"
                print(f"  {scope:<20} {k:<44} {current(data, k)!r} {mark} {v!r}")
            if todo and args.apply:
                try:
                    admin.post("LabelManager/action/saveLabels",
                               {"scope": scope, "language": LANGUAGE, "labels": todo})
                    changed += len(todo)
                except RuntimeError as exc:
                    print(f"  ! {scope}: {exc}")
                    failed += 1
            elif todo:
                changed += len(todo)
        if args.apply and changed:
            admin.post("Admin/clearCache", {})
    except httpx.HTTPError as exc:
        print(f"Could not reach the CRM: {exc}", file=sys.stderr)
        return 3
    print()
    if args.apply:
        print(f"{changed} label(s) written, cache cleared." if changed else "Nothing to do — every label already matches.")
    else:
        print(f"Dry run only. {changed} label(s) would change. Re-run with --apply.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
