"""Label the lead entity and its links "Outreach Lead" in the CRM (ruling 50).

The lead model (rulings 41-50) renames the prospect record a **lead**. The
stored entity stays ``CProspect``; only what staff read in the CRM changes.
EspoCRM ships its own hidden ``Lead`` entity, so the CRM label is "Outreach
Lead" (ruling 35's rule: a custom entity never takes a built-in name), and the
application's screens say "Lead".

**What it changes**, through EspoCRM's Label Manager, language ``en_US``:

* the entity: ``scopeNames`` / ``scopeNamesPlural`` of ``CProspect``;
* the links that point at it: Contact and Account ``cProspectRecords``,
  Account ``cAlreadyKnownProspects``, COutreachTouch ``prospect``;
* the lead's own three links to a Company or Contact
  (``promotedCompany``, ``promotedContact``, ``alreadyKnownCompany``), whose
  labels named promotion and "already known".

Labels only. No stored name changes, no data changes, no application code
reads a label. Idempotent; **dry-run by default**; needs an Admin-type login,
run through ``scripts/run_with_admin.py``::

    PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/relabel_outreach_lead.py
    PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/relabel_outreach_lead.py --apply

Another CRM: ``run_with_admin.py --env <file>``. Undo: ``--undo --apply``
writes back the labels read on crm-test before the change (``BEFORE``).

Exit codes: 0 done, 1 a write failed, 2 no credential, 3 unreachable.
"""
from __future__ import annotations

import argparse
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from relabel_outreach_campaign import Admin, current  # noqa: E402

ENTITY = "CProspect"

#: {scope: {"category[.]key": label}} — every label this script owns.
WANTED: dict[str, dict[str, str]] = {
    "Global": {f"scopeNames[.]{ENTITY}": "Outreach Lead", f"scopeNamesPlural[.]{ENTITY}": "Outreach Leads"},
    "Contact": {"links[.]cProspectRecords": "Outreach Leads", "fields[.]cProspectRecords": "Outreach Leads"},
    "Account": {"links[.]cProspectRecords": "Outreach Leads", "fields[.]cProspectRecords": "Outreach Leads",
                "links[.]cAlreadyKnownProspects": "Duplicate outreach leads",
                "fields[.]cAlreadyKnownProspects": "Duplicate outreach leads"},
    "COutreachTouch": {"links[.]prospect": "Outreach Lead", "fields[.]prospect": "Outreach Lead"},
    "CProspect": {"links[.]promotedCompany": "Converted to company", "fields[.]promotedCompany": "Converted to company",
                  "links[.]promotedContact": "Converted to contact", "fields[.]promotedContact": "Converted to contact",
                  "links[.]alreadyKnownCompany": "Duplicate of company",
                  "fields[.]alreadyKnownCompany": "Duplicate of company"},
}

#: The labels read on crm-test 10-19-26 before the change, for ``--undo``.
BEFORE: dict[str, dict[str, str]] = {
    "Global": {f"scopeNames[.]{ENTITY}": "Prospect", f"scopeNamesPlural[.]{ENTITY}": "Prospects"},
    "Contact": {"links[.]cProspectRecords": "Prospect records", "fields[.]cProspectRecords": "Prospect records"},
    "Account": {"links[.]cProspectRecords": "Prospect records", "fields[.]cProspectRecords": "Prospect records",
                "links[.]cAlreadyKnownProspects": "Already-known prospects",
                "fields[.]cAlreadyKnownProspects": "Already-known prospects"},
    "COutreachTouch": {"links[.]prospect": "Prospect", "fields[.]prospect": "Prospect"},
    "CProspect": {"links[.]promotedCompany": "Promoted to company", "fields[.]promotedCompany": "Promoted to company",
                  "links[.]promotedContact": "Promoted to contact", "fields[.]promotedContact": "Promoted to contact",
                  "links[.]alreadyKnownCompany": "Already known as",
                  "fields[.]alreadyKnownCompany": "Already known as"},
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Label the lead entity and its links 'Outreach Lead' (ruling 50).")
    ap.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    ap.add_argument("--undo", action="store_true", help="write back BEFORE instead")
    args = ap.parse_args()
    base = os.environ.get("ESPO_ADMIN_BASE") or os.environ.get("ADMIN_BASE")
    user = os.environ.get("ESPO_ADMIN_USER") or os.environ.get("ADMIN_USER")
    password = os.environ.get("ESPO_ADMIN_PASS") or os.environ.get("ADMIN_PASS")
    if not (base and user and password):
        print("No admin credential — run through scripts/run_with_admin.py.", file=sys.stderr)
        return 2
    target = BEFORE if args.undo else WANTED
    if not target:
        print("Nothing recorded to undo to.", file=sys.stderr)
        return 1
    print(f"CRM:  {base}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN - nothing will change'}{' (undo)' if args.undo else ''}\n")
    admin = Admin(base, user, password)
    failed = changed = 0
    try:
        for scope, labels in target.items():
            data = admin.scope_data(scope)
            todo = {k: v for k, v in labels.items() if current(data, k) != v}
            for k, v in labels.items():
                mark = "->" if k in todo else "ok"
                print(f"  {scope:<16} {k:<40} {current(data, k)!r} {mark} {v!r}")
            if todo and args.apply:
                try:
                    admin.post("LabelManager/action/saveLabels",
                               {"scope": scope, "language": "en_US", "labels": todo})
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
