"""Give one sandbox Contact a real address — a crm-test fixture for the pull.

The unsubscribe pull (plan § 11.6) matches the vendor's unsubscribed addresses
against CRM Contacts. Proving its CRM write needs a Contact whose address a
real person unsubscribed at the vendor, and every sandbox Contact carries an
invented address. This sets the primary email of ONE opted-in sandbox Contact
(the first of the three ``sandbox_mailing_optin.py`` ticked) to the address
given, so the pull's dry run says "would be marked opted out" and its apply
marks it. The nightly reset restores the sandbox address.

Refuses to run against anything but crm-test. Reads credentials from ``.env``
without a shell.

Run::

    uv run scripts/sandbox_adopt_email.py someone@example.org
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
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        print("usage: sandbox_adopt_email.py ADDRESS")
        return 2
    address = sys.argv[1].strip()
    env = _env()
    base, key = env.get("ESPO_BASE_URL", ""), env.get("ESPO_API_KEY", "")
    if "crm-test" not in base:
        print(f"refusing: {base or '(no ESPO_BASE_URL)'} is not crm-test")
        return 2
    h = {"X-Api-Key": key}
    r = httpx.get(
        f"{base}/api/v1/Contact",
        params=[("maxSize", "5"), ("orderBy", "name"),
                ("select", "name,emailAddress,emailAddressData"),
                ("where[0][type]", "isTrue"), ("where[0][attribute]", "cMarketingOptIn")],
        headers=h, timeout=30,
    )
    r.raise_for_status()
    rows = r.json()["list"]
    if not rows:
        print("no opted-in sandbox Contact — run sandbox_mailing_optin.py first")
        return 1
    c = rows[0]
    data = [{"emailAddress": address, "primary": True, "optOut": False, "invalid": False}]
    u = httpx.put(f"{base}/api/v1/Contact/{c['id']}", json={"emailAddressData": data},
                  headers=h, timeout=30)
    back = httpx.get(f"{base}/api/v1/Contact/{c['id']}",
                     params={"select": "name,emailAddress,emailAddressIsOptedOut"},
                     headers=h, timeout=30).json()
    print(f"HTTP {u.status_code}  {back.get('name')}  primary email now <{back.get('emailAddress')}>"
          f"  optedOut={back.get('emailAddressIsOptedOut')}  (was <{c.get('emailAddress')}>)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
