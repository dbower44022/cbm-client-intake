"""Pre-flight: can an accidental Save in the sandbox reach the real world?

Doug's ruling 2026-08-21: nobody is supposed to save anything during training,
but the sandbox has to be safe on the assumption that somebody will.  That
makes containment a property to CHECK before a session, not a policy to write
down — a checklist nobody runs is how this fails quietly.

What an accidental save can reach, and what stops it:

* **Outbound email and calendar** both go out by domain-wide delegation
  impersonating the signed-in user's ``CMentorProfile.cbmEmail``
  (``comms/service.py``; the staff quick-compose falls back to the same
  per-user identity when ``OPS_MAILBOX`` is unset).  An address with no Google
  mailbox 403s ``unauthorized_client``, the call fails best-effort, and nothing
  reaches a real person.  So **every training identity's ``cbmEmail`` must be
  an address that does not exist.**
* **Drive is the exception and cbmEmail does not help.** Uploads run as the
  service account (``GDRIVE_IDENTITY=service``), so a document saved in the
  sandbox lands in whatever shared drive the app is pointed at — today the
  *production* one.  Only a separate sandbox drive fixes that.
* **Mentor provisioning** can create real Workspace accounts, but only with
  the Google Directory flags on.  They must stay off here.
* **``OPS_MAILBOX``** arms sending as info@ and the inbound poller.  It must
  stay unset on crm-test — and note only ONE deployment may poll info@.

Read-only: reads the two App Platform specs via ``doctl`` and the mentor roster
over the CRM API.  Prints no secret values.

    uv run python scripts/sandbox/check_containment.py
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.config import get_settings  # noqa: E402
from core.espo import EspoClient, EspoError  # noqa: E402

#: Every training identity's cbmEmail must sit on this domain, which has no
#: Workspace mailboxes. An address anywhere else can genuinely send mail and
#: raise calendar invites, so it is a containment breach, not a warning.
SANDBOX_EMAIL_DOMAIN = "sandbox.cbmentors.org"

SANDBOX_APP = "509b4370-b9ca-42c7-b251-04d6820fe88e"
PROD_APP = "aa1ddf69-f359-4b53-91ba-035cbed7bd53"

OK, WARN, BAD = "  ok  ", " WARN ", " FAIL "


def app_envs(app_id: str) -> dict[str, str]:
    """Every env var across an app's web + worker, secrets reduced to a marker."""
    raw = subprocess.run(
        ["doctl", "apps", "get", app_id, "-o", "json"],
        capture_output=True, text=True, check=True,
    ).stdout
    spec = json.loads(raw)[0]["spec"]
    envs: dict[str, str] = {}
    for component in spec.get("services", []) + spec.get("workers", []):
        for entry in component.get("envs", []):
            value = entry.get("value", "")
            if entry.get("type") == "SECRET" or "EV[" in str(value):
                value = "<secret>"
            envs[entry["key"]] = value
    return envs


def truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def check_deployment() -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    sandbox = app_envs(SANDBOX_APP)
    prod = app_envs(PROD_APP)

    crm = sandbox.get("ESPO_BASE_URL", "")
    findings.append(
        (OK if "crm-test" in crm.lower() else BAD, f"sandbox CRM is {crm or '(unset)'}")
    )

    sandbox_drive = sandbox.get("GDRIVE_SHARED_DRIVE_ID", "")
    prod_drive = prod.get("GDRIVE_SHARED_DRIVE_ID", "")
    if not truthy(sandbox.get("GDRIVE_DOCS", "")):
        findings.append((OK, "Drive documents are off — uploads cannot leave"))
    elif sandbox_drive and sandbox_drive == prod_drive:
        findings.append(
            (BAD, "Drive uploads land in the PRODUCTION shared drive "
                  f"({sandbox_drive}) — point the sandbox at its own")
        )
    elif sandbox_drive:
        findings.append((OK, f"sandbox has its own shared drive ({sandbox_drive})"))
    else:
        findings.append((WARN, "GDRIVE_DOCS on with no shared drive configured"))

    if sandbox.get("OPS_MAILBOX"):
        findings.append(
            (BAD, f"OPS_MAILBOX is set ({sandbox['OPS_MAILBOX']}) — the sandbox "
                  "can send as info@ and will double-poll the shared inbox")
        )
    else:
        findings.append((OK, "OPS_MAILBOX unset — no info@ sending, no inbound poller"))

    for flag in ("GOOGLE_CREATE_MAILBOX", "GOOGLE_DIRECTORY_CHECK", "GOOGLE_MEMBERS_GROUP"):
        value = sandbox.get(flag, "")
        if value and truthy(value):
            findings.append((BAD, f"{flag} is on — provisioning can create real Google accounts"))
        else:
            findings.append((OK, f"{flag} off — provisioning cannot create Google accounts"))

    for flag, label in (("GCAL_EVENTS", "calendar writes"), ("GMAIL_SYNC", "email")):
        if truthy(sandbox.get(flag, "")):
            findings.append(
                (WARN, f"{flag} on — {label} are live; containment rests entirely on "
                       "every training cbmEmail being a non-existent mailbox")
            )
    return findings


async def check_identities() -> list[tuple[str, str]]:
    """List the cbmEmail every sandbox login would send and invite as.

    This cannot prove a mailbox does not exist without Directory access, so it
    reports the addresses for a human to confirm — the useful failure it does
    catch is a training profile carrying a REAL @cbmentors.org address that
    someone copied from production.
    """
    settings = get_settings()
    if "crm-test" not in (settings.espo_base_url or "").lower():
        return [(BAD, f"ESPO_BASE_URL is {settings.espo_base_url!r}, not crm-test — skipped")]
    client = EspoClient(settings.espo_base_url, settings.espo_api_key,
                        settings.request_timeout_seconds)
    try:
        # 200 is EspoCRM's recordListMaxSizeLimit — asking for more is a 403,
        # not a truncation. The sandbox roster is well inside one page.
        envelope = await client.list(
            "CMentorProfile", select="name,cbmEmail,mentorStatus", max_size=200
        )
    except EspoError as exc:
        return [(WARN, f"could not read the mentor roster: {exc}")]
    rows = envelope.get("list", [])

    addressed = [r for r in rows if (r.get("cbmEmail") or "").strip()]
    findings = [(OK, f"{len(rows)} mentor profiles, {len(addressed)} carrying a cbmEmail")]

    offdomain = [r for r in addressed
                 if not (r.get("cbmEmail") or "").strip().lower()
                 .endswith("@" + SANDBOX_EMAIL_DOMAIN)]
    if offdomain:
        for row in sorted(offdomain, key=lambda r: (r.get("cbmEmail") or "").lower()):
            findings.append(
                (BAD, f"{row.get('cbmEmail')} ({row.get('name')}) is NOT on "
                      f"@{SANDBOX_EMAIL_DOMAIN} — it can send mail and raise "
                      "calendar invites if somebody saves")
            )
    else:
        findings.append(
            (OK, f"every cbmEmail is on @{SANDBOX_EMAIL_DOMAIN}, which has no "
                 "mailboxes — an accidental Save cannot reach anyone")
        )
    return findings


async def main() -> int:
    print("\nSandbox containment — what an accidental Save could reach\n")
    findings = check_deployment()
    print("Deployment configuration")
    for mark, line in findings:
        print(f"[{mark}] {line}")

    print("\nSending identities")
    identity_findings = await check_identities()
    for mark, line in identity_findings:
        print(f"[{mark}] {line}" if mark.strip() else line)

    failures = sum(1 for mark, _ in findings + identity_findings if mark == BAD)
    print(f"\n{failures} blocking issue(s).\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
