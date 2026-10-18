"""The CRM's own screens for the three prospect-marketing entities, and the
read-back that proves the Phase 1 change from outside.

``coutreach-entities-crm-handoff.md`` § 3.2 and § 3.3, as a script so the same
change runs from inside the production web container (on crm-test it was done
through the admin API by hand on 10-15-26):

* **Tab list** (§ 3.2): Prospects and Campaigns placed after Information
  Requests; Touches removed (touches are reached from a campaign and a
  prospect record, never from a tab). EspoCRM appends every new entity at the
  end of the list, Touches included.
* **Layouts** (§ 3.3): a new entity's default detail layout carries only
  ``name``, so every plan field and many-to-one link goes into a *Details*
  panel; each list layout gains five columns.

Additive and idempotent: a tab already placed, a field already on a layout, a
column already listed is left alone; nothing is removed from a layout. Dry run
by default. Needs an Admin-type login (``ESPO_ADMIN_BASE`` / ``_USER`` /
``_PASS``; inside a container they are exported from the provisioning admin).

``--verify`` changes nothing and needs no admin: as the ORG-WIDE API KEY
(``ESPO_BASE_URL`` / ``ESPO_API_KEY``, the application's own credential) it
reads ``GET /<Entity>?maxSize=1`` for the three entities (200 is right, even
empty; 403 is a missed grant) and the metadata of § 5 step 1.

    PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/apply_outreach_ui.py          # dry run
    ... scripts/apply_outreach_ui.py --apply
    PYTHONPATH=. uv run python scripts/apply_outreach_ui.py --verify

Exit codes: 0 done / verified, 1 something failed, 2 no credential.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

NEW = ("CProspect", "COutreachCampaign", "COutreachTouch")
ON_TABS = ("CProspect", "COutreachCampaign")
OFF_TABS = ("COutreachTouch",)
AFTER = "CInformationRequest"
LIST_COLUMNS = {
    "CProspect": ("name", "funnelStage", "entryDoor", "sideExit", "website"),
    "COutreachCampaign": ("name", "campaignKind", "campaignStatus", "startDate", "endDate"),
    "COutreachTouch": ("name", "channel", "touchStatus", "outcome", "outreachCampaign"),
}


def _plan() -> dict[str, Any]:
    return json.loads((REPO / "scripts/plans/coutreach-entities.json").read_text())


def wanted_detail_fields(plan: dict[str, Any], entity: str) -> list[str]:
    fields = [f["name"] for f in plan["fields"] if f["entity"] == entity]
    links = [l["link"] for l in plan["links"] if l["entity"] == entity and l["linkType"] == "manyToOne"]
    return fields + links


def layout_fields(layout: Any) -> set[str]:
    out: set[str] = set()
    for panel in layout or []:
        for row in (panel or {}).get("rows") or []:
            for cell in row or []:
                if isinstance(cell, dict) and cell.get("name"):
                    out.add(cell["name"])
    return out


def wanted_tabs(tabs: list[Any]) -> list[Any]:
    out = [t for t in tabs if not (isinstance(t, str) and t in ON_TABS + OFF_TABS)]
    names = [t for t in out if isinstance(t, str)]
    at = out.index(AFTER) + 1 if AFTER in names else len(out)
    out[at:at] = list(ON_TABS)
    return out


async def run(apply: bool) -> int:
    from espo_admin import connect, load_env  # noqa: E402  (scripts/ on sys.path)

    client, profile = await connect(load_env())
    if profile.get("type") != "admin":
        print(f"{profile.get('userName')} is type={profile.get('type')}; this needs an Admin-type account.")
        return 2
    base = client._base
    print(f"CRM:  {base}\nUser: {profile.get('userName')} (type=admin)\n"
          f"Mode: {'APPLY' if apply else 'DRY RUN - nothing will change'}\n")
    changes: list[str] = []
    failed: list[str] = []

    for entity in NEW:
        scope = await client._request("GET", f"{base}/Metadata", op="m", params={"key": f"scopes.{entity}"})
        if scope.status_code != 200 or not scope.content:
            print(f"{entity} does not exist on this CRM - apply scripts/plans/coutreach-entities.json first.")
            return 2

    # --- tab list -----------------------------------------------------------
    r = await client._request("GET", f"{base}/Settings", op="settings")
    tabs = r.json().get("tabList") or []
    target = wanted_tabs(tabs)
    if target != tabs:
        changes.append("tab list: Prospects and Campaigns after Information Requests; Touches removed")
        if apply:
            w = await client._request("PUT", f"{base}/Settings", op="tabs", json_body={"tabList": target})
            back = (await client._request("GET", f"{base}/Settings", op="settings")).json().get("tabList") or []
            if w.status_code >= 300 or back != target:
                failed.append(f"tab list -> HTTP {w.status_code}; read-back differs")

    # --- layouts --------------------------------------------------------------
    plan = _plan()
    for entity in NEW:
        r = await client._request("GET", f"{base}/{entity}/layout/detail", op="layout")
        layout = r.json() if r.status_code == 200 else []
        have = layout_fields(layout)
        missing = [f for f in wanted_detail_fields(plan, entity) if f not in have]
        if missing:
            changes.append(f"{entity} detail layout: add {len(missing)} field(s) in a Details panel")
            if apply:
                rows, pair = [], []
                for f in missing:
                    pair.append({"name": f})
                    if len(pair) == 2:
                        rows.append(pair); pair = []
                if pair:
                    rows.append(pair + [False])
                new = list(layout or []) + [{"label": "Details", "rows": rows}]
                w = await client._request("PUT", f"{base}/{entity}/layout/detail", op="layout", json_body=new)
                back = await client._request("GET", f"{base}/{entity}/layout/detail", op="layout")
                still = [f for f in missing if f not in layout_fields(back.json())]
                if w.status_code >= 300 or still:
                    failed.append(f"{entity} detail layout -> HTTP {w.status_code}; still missing {still}")
        r = await client._request("GET", f"{base}/{entity}/layout/list", op="layout")
        cols = r.json() if r.status_code == 200 and isinstance(r.json(), list) else []
        have_cols = [c.get("name") for c in cols if isinstance(c, dict)]
        add = [c for c in LIST_COLUMNS[entity] if c not in have_cols]
        if add:
            changes.append(f"{entity} list layout: add columns {', '.join(add)}")
            if apply:
                w = await client._request("PUT", f"{base}/{entity}/layout/list", op="layout",
                                          json_body=cols + [{"name": c} for c in add])
                if w.status_code >= 300:
                    failed.append(f"{entity} list layout -> HTTP {w.status_code}")

    if apply and changes:
        await client._request("POST", f"{base}/Admin/clearCache", op="cache", json_body={})

    title = "CHANGED" if apply else "WOULD CHANGE"
    if changes:
        print(f"{title}:")
        for c in changes:
            print(f"  - {c}")
    else:
        print("Nothing to do - the tab list and the layouts already match.")
    if failed:
        print("FAILED:")
        for f in failed:
            print(f"  ! {f}")
    if not apply and changes:
        print("\nDry run only. Re-run with --apply to make these changes.")
    return 1 if failed else 0


def verify() -> int:
    """As the org-wide API key: the three list reads and the shape (§ 5 steps 1-2)."""
    base = (os.environ.get("ESPO_BASE_URL") or "").rstrip("/")
    key = os.environ.get("ESPO_API_KEY") or ""
    if not (base and key):
        print("ESPO_BASE_URL and ESPO_API_KEY are needed (the application's own credential).")
        return 2
    api = base + "/api/v1"
    h = {"X-Api-Key": key}
    ok = True
    with httpx.Client(timeout=30) as c:
        print(f"CRM: {base} (as the org-wide API key)\n")
        for e in NEW:
            r = c.get(f"{api}/{e}", params={"maxSize": 1}, headers=h)
            good = r.status_code == 200
            ok &= good
            print(f"  {'ok ' if good else 'BAD'} GET /{e}?maxSize=1 -> {r.status_code}")

        def meta(k: str) -> Any:
            r = c.get(f"{api}/Metadata", params={"key": k}, headers=h)
            return r.json() if r.status_code == 200 and r.content else None

        checks = [
            ("Contact.cSmsOptIn is bool", (meta("entityDefs.Contact.fields.cSmsOptIn") or {}).get("type") == "bool"),
            ("CProspect.mailingAddress is address", (meta("entityDefs.CProspect.fields.mailingAddress") or {}).get("type") == "address"),
            ("COutreachCampaign.description is wysiwyg", (meta("entityDefs.COutreachCampaign.fields.description") or {}).get("type") == "wysiwyg"),
            ("CEngagement.referringPartners -> CPartnerProfile", (meta("entityDefs.CEngagement.links.referringPartners") or {}).get("entity") == "CPartnerProfile"),
            ("COutreachCampaign.attributedPartnerProfiles exists", bool(meta("entityDefs.COutreachCampaign.links.attributedPartnerProfiles"))),
            ("Account.cCompanyType offers Prospect", "Prospect" in ((meta("entityDefs.Account.fields.cCompanyType") or {}).get("options") or [])),
            ("CIntakeSubmission.form offers Prospect Response", "Prospect Response" in ((meta("entityDefs.CIntakeSubmission.fields.form") or {}).get("options") or [])),
            ("no double prefix (scopes.CCProspect empty)", meta("scopes.CCProspect") is None),
        ]
        for label, good in checks:
            ok &= bool(good)
            print(f"  {'ok ' if good else 'BAD'} {label}")
    print("\nAll checks passed." if ok else "\nSome checks FAILED - see the BAD lines.")
    return 0 if ok else 1


def main() -> int:
    if "--verify" in sys.argv:
        return verify()
    sys.path.insert(0, str(REPO / "scripts"))
    return asyncio.run(run("--apply" in sys.argv))


if __name__ == "__main__":
    raise SystemExit(main())
