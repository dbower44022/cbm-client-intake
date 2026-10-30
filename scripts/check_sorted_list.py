"""Check a CRM's multi-column sorted list endpoint — read-only.

sorted-list-crm-handoff.md § 3 as one command: after
``scripts/install_sorted_list.sh <chapter>``, this proves the endpoint answers,
sorts on two columns, and refuses what it should. It reads; it never writes.

Run through ``scripts/check_sorted_list.sh <chapter>`` (it supplies the
administrator credential without printing it). Exit 0 = every check passed.

Checks:

1. ``GET SortedList/Account?orderList=name:desc,id:asc&maxSize=20`` answers
   200 with rows, and the names come back Z→A.
2. Two columns: ``cCompanyType:asc,name:asc`` — inside each type the names are A→Z.
3. An unknown column is refused (400).
4. A page over 200 is refused.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from espo_admin import connect, load_env  # noqa: E402

from core.espo import EspoError  # noqa: E402


async def _get(client, query: str) -> tuple[int, dict]:
    resp = await client._request("GET", f"{client._base}/SortedList/Account?{query}",
                                 op="check sorted list")
    try:
        body = resp.json()
    except ValueError:
        body = {}
    return resp.status_code, body if isinstance(body, dict) else {}


def _key(v) -> str:
    if isinstance(v, list):          # a multi-enum (cCompanyType) is a list
        v = ",".join(str(x) for x in v)
    return (v or "").casefold()


async def main() -> int:
    client, profile = await connect(load_env())
    print(f"CRM: {client._base}  (as {profile.get('userName')})")
    failed = 0

    def report(ok: bool, what: str) -> None:
        nonlocal failed
        print(("  PASS  " if ok else "  FAIL  ") + what)
        failed += 0 if ok else 1

    try:
        code, body = await _get(client, "orderList=name:desc,id:asc&maxSize=20&select=name")
        rows = body.get("list", [])
        names = [_key(r.get("name")) for r in rows]
        report(code == 200 and bool(rows) and names == sorted(names, reverse=True),
               f"answers and sorts one column Z→A (HTTP {code}, {len(rows)} rows)")
        if code == 404:
            print("\nThe endpoint is not installed on this CRM. Run "
                  "scripts/install_sorted_list.sh first.")
            return 1

        code, body = await _get(client, "orderList=cCompanyType:asc,name:asc&maxSize=200&select=name,cCompanyType")
        rows = body.get("list", [])
        ok = code == 200 and bool(rows)
        for a, b in zip(rows, rows[1:]):
            if _key(a.get("cCompanyType")) == _key(b.get("cCompanyType")) and _key(a.get("name")) > _key(b.get("name")):
                ok = False
        report(ok, f"sorts on two columns, company type then name (HTTP {code}, {len(rows)} rows)")

        code, _ = await _get(client, "orderList=noSuchColumn:asc&maxSize=5")
        report(code == 400, f"refuses an unknown column (HTTP {code}, wants 400)")

        code, _ = await _get(client, "orderList=name:asc&maxSize=201")
        report(code in (400, 403), f"refuses a page over 200 (HTTP {code})")
    except EspoError as exc:
        report(False, f"the CRM refused the check: {exc}")

    print("\nAll checks passed." if not failed else f"\n{failed} check(s) failed.")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
