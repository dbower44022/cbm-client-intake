"""Prove the partner-host link removal from the data, not the screen.

Reads ``entityDefs`` from the CRM named in ``.env`` as the application's own
API key (a read-only metadata call) and prints one line per link: the old
single ``CEvent.partnerHost`` must be gone, the many-to-many
``CEvent.partnerProfiles`` / ``CPartnerProfile.sponsoredEvents`` must be
present and point at each other. Exit code 0 and a final ``OK`` when all three
hold. Runbook: ``cevent-partner-sponsorship-crm-handoff.md`` § 5 and § 6.

Run from the repository root::

    uv run python scripts/check_partner_host_removed.py

``.env`` is parsed, never sourced by a shell (a password's punctuation would
be interpreted). Pass ``--base URL --key KEY`` to check another CRM.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import httpx


def _env() -> dict[str, str]:
    out: dict[str, str] = {}
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        m = re.match(r"\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out


def main() -> int:
    args = sys.argv[1:]
    env = _env()
    base = args[args.index("--base") + 1] if "--base" in args else env.get("ESPO_BASE_URL", "")
    key = args[args.index("--key") + 1] if "--key" in args else env.get("ESPO_API_KEY", "")
    if not (base and key):
        print("Need ESPO_BASE_URL and ESPO_API_KEY in .env, or --base and --key.", file=sys.stderr)
        return 2
    api = base.rstrip("/") + "/api/v1/Metadata"
    headers = {"X-Api-Key": key}

    def read(k: str):
        r = httpx.get(api, params={"key": k}, headers=headers, timeout=30)
        r.raise_for_status()
        return r.json() if r.content else None

    ok = True
    old = read("entityDefs.CEvent.links.partnerHost")
    if old:
        ok = False
        print(f"partnerHost: STILL PRESENT -> {old.get('entity')} ({old.get('foreign')})")
    else:
        print("partnerHost: gone")
    near = read("entityDefs.CEvent.links.partnerProfiles") or {}
    far = read("entityDefs.CPartnerProfile.links.sponsoredEvents") or {}
    if near.get("entity") == "CPartnerProfile" and near.get("foreign") == "sponsoredEvents":
        print(f"partnerProfiles: present -> {near['entity']} ({near['foreign']})")
    else:
        ok = False
        print(f"partnerProfiles: WRONG OR MISSING -> {near}")
    if far.get("entity") == "CEvent" and far.get("foreign") == "partnerProfiles":
        print(f"CPartnerProfile.sponsoredEvents: present -> {far['entity']} ({far['foreign']})")
    else:
        ok = False
        print(f"CPartnerProfile.sponsoredEvents: WRONG OR MISSING -> {far}")
    print("OK" if ok else "NOT OK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
