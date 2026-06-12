"""Request-for-information -> Contact (Prospect), optional Account.

Mapping (reconciled against crm-test.clevelandbusinessmentors.org, 2026-06-12):

  * Contact — find-or-create by email. New contacts get
    cContactType=["Prospect"] (option added to crm-test 2026-06) and the
    message in `description`, stamped with date and source.
  * Existing contact — the stamped message is APPENDED to the existing
    description (never overwritten — it may hold staff notes). The contact's
    type and links are left untouched: an existing Client asking a question
    is not a new Prospect. Requires *edit* on Contact for the intake API user.
  * Account — created/linked only when a company name is given AND the contact
    is new (linking would otherwise risk detaching an existing contact's
    account). Find-or-create by name like client-intake; on create it gets
    cAccountType=["Client"] (required discriminator; nearest fit) and
    cClientStatus="Prospect" — the staff worklist marker. A matched existing
    Account keeps its current status.
  * No CClientProfile / CEngagement — those represent an actual mentoring
    relationship; client-intake creates them if the prospect converts.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from core.espo import EspoApi
from core.phone import to_e164

from .schemas import InfoRequest

log = logging.getLogger("cbm_intake.orchestrator")

ACCOUNT = "Account"
CONTACT = "Contact"

A_ACCOUNT_TYPE = "cAccountType"    # multiEnum on Account — REQUIRED
A_COMPANY_TYPE = "cCompanyType"    # multiEnum on Account (legacy, kept in sync)
A_CLIENT_STATUS = "cClientStatus"  # enum on Account
C_CONTACT_TYPE = "cContactType"    # multiEnum on Contact

CLIENT = "Client"
PROSPECT = "Prospect"


def _description_block(sub: InfoRequest, *, include_company: bool) -> str:
    """The stamped, human-readable note staff will read on the Contact."""
    lines = [f"[Information request via website — {datetime.now(timezone.utc):%Y-%m-%d}]"]
    if include_company and sub.company:
        lines.append(f"Company: {sub.company}")
    if sub.how_did_you_hear:
        lines.append(f"How they heard about CBM: {sub.how_did_you_hear}")
    lines.append("")
    lines.append(sub.message.strip())
    return "\n".join(lines)


async def _find_or_create_account(sub: InfoRequest, client: EspoApi) -> str:
    existing = await client.find_one(ACCOUNT, "name", sub.company)
    if existing:
        log.info("matched existing Account %s for %r", existing["id"], sub.company)
        return existing["id"]
    created = await client.create(
        ACCOUNT,
        {
            "name": sub.company,
            A_ACCOUNT_TYPE: [CLIENT],
            A_COMPANY_TYPE: [CLIENT],
            A_CLIENT_STATUS: PROSPECT,
        },
    )
    return created["id"]


async def submit_request(sub: InfoRequest, client: EspoApi) -> dict[str, str]:
    existing = await client.find_one(
        CONTACT, "emailAddress", str(sub.email), select="id,description"
    )
    if existing:
        prior = (existing.get("description") or "").rstrip()
        block = _description_block(sub, include_company=True)
        description = f"{prior}\n\n{block}" if prior else block
        await client.update(CONTACT, existing["id"], {"description": description})
        log.info("appended info request to existing Contact %s", existing["id"])
        return {"contactId": existing["id"]}

    account_id = await _find_or_create_account(sub, client) if sub.company else None
    payload = {
        "firstName": sub.first_name,
        "lastName": sub.last_name,
        "emailAddress": str(sub.email),
        C_CONTACT_TYPE: [PROSPECT],
        "description": _description_block(sub, include_company=False),
    }
    if sub.phone:
        payload["phoneNumber"] = to_e164(sub.phone)
    if account_id:
        payload["accountId"] = account_id
    created = await client.create(CONTACT, payload)

    ids = {"contactId": created["id"]}
    if account_id:
        ids["accountId"] = account_id
    return ids
