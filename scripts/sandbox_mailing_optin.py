"""Tick the marketing opt-in on three sandbox Contacts — a crm-test test fixture.

The mailing-list push (plan § 11.5) needs an audience to prove itself, and the
sandbox's 58 Contacts all carry invented addresses at the sandbox domain with
the opt-in unticked. This sets ``cMarketingOptIn`` on three of them (distinct
surnames, nobody typed Mentor) so the Operations job's dry run shows three ADD
lines. The nightly reset clears it.

Refuses to run against anything but crm-test. Reads credentials from ``.env``
without a shell (see the never-read-.env-with-a-shell rule).

Run::

    uv run python scripts/sandbox_mailing_optin.py          # set the three
    uv run python scripts/sandbox_mailing_optin.py --clear  # untick them again
"""

from __future__ import annotations

import pathlib
import re
import sys

import httpx

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env").read_text().splitlines():
        m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out


def main() -> int:
    clear = "--clear" in sys.argv
    env = _env()
    base, key = env.get("ESPO_BASE_URL", ""), env.get("ESPO_API_KEY", "")
    if "crm-test" not in base:
        print(f"refusing: {base or '(no ESPO_BASE_URL)'} is not crm-test")
        return 2
    h = {"X-Api-Key": key}
    r = httpx.get(
        f"{base}/api/v1/Contact",
        params=[("maxSize", "200"), ("orderBy", "name"),
                ("select", "name,firstName,lastName,emailAddress,cContactType,cMarketingOptIn")],
        headers=h, timeout=30,
    )
    r.raise_for_status()
    rows = r.json()["list"]
    if clear:
        picked = [c for c in rows if c.get("cMarketingOptIn")]
    else:
        picked, seen = [], set()
        for c in rows:
            if not (c.get("emailAddress") and c.get("firstName") and c.get("lastName")):
                continue
            if "Mentor" in (c.get("cContactType") or []) or c["lastName"] in seen:
                continue
            seen.add(c["lastName"])
            picked.append(c)
            if len(picked) == 3:
                break
    for c in picked:
        u = httpx.put(f"{base}/api/v1/Contact/{c['id']}",
                      json={"cMarketingOptIn": not clear}, headers=h, timeout=30)
        back = httpx.get(f"{base}/api/v1/Contact/{c['id']}",
                         params={"select": "cMarketingOptIn,emailAddressIsOptedOut,emailAddressIsInvalid"},
                         headers=h, timeout=30).json()
        print(f"HTTP {u.status_code}  {c['name']} <{c['emailAddress']}>  optIn={back.get('cMarketingOptIn')}"
              f"  optedOut={back.get('emailAddressIsOptedOut')}  invalid={back.get('emailAddressIsInvalid')}")
    total = httpx.get(
        f"{base}/api/v1/Contact",
        params=[("maxSize", "1"), ("where[0][type]", "isTrue"), ("where[0][attribute]", "cMarketingOptIn")],
        headers=h, timeout=30,
    ).json().get("total")
    print(f"audience on crm-test now: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
