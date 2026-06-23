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
  * CInformationRequest — a dedicated, self-contained record of the request
    (requester name/email/phone/company/message/source/status), linked to the
    Contact (and Account when one is involved). Created best-effort on every
    submission, ON TOP OF the Contact.description stamp and the generic
    CIntakeSubmission log (see cinformation-request-entity.md). The entity is a
    CRM-team build; until it (and the API user's create grant) exist, the write
    fails and is logged at WARNING — the submission still succeeds.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from core.espo import EspoApi
from core.phone import e164_or_none

from .schemas import InfoRequest

log = logging.getLogger("cbm_intake.orchestrator")

ACCOUNT = "Account"
CONTACT = "Contact"
INFO_REQUEST = "CInformationRequest"  # dedicated entity (see cinformation-request-entity.md)
FORM_SLUG = "info-request"  # value written to CInformationRequest.form

A_ACCOUNT_TYPE = "cAccountType"    # multiEnum on Account — REQUIRED
A_COMPANY_TYPE = "cCompanyType"    # multiEnum on Account (legacy, kept in sync)
A_CLIENT_STATUS = "cClientStatus"  # enum on Account
C_CONTACT_TYPE = "cContactType"    # multiEnum on Contact

CLIENT = "Client"
PROSPECT = "Prospect"
REQUEST_STATUS_NEW = "New"


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


def _submission_json(sub: InfoRequest) -> str:
    """The raw submission as a readable note + JSON, for the entity's description
    (mirrors the CIntakeSubmission audit record)."""
    data = json.loads(sub.model_dump_json())
    data["company_url"] = ""            # clear the honeypot field
    data.pop("submission_token", None)  # internal idempotency token, not useful here
    body = json.dumps(data, indent=2, sort_keys=True)
    return (
        "Information request submitted via the website.\n\n"
        "----- submission payload -----\n" + body
    )


async def _create_information_request(
    sub: InfoRequest, client: EspoApi, contact_id: str, account_id: str | None
) -> str | None:
    """Create the dedicated CInformationRequest record, linked to the Contact.

    BEST-EFFORT: a failure (entity/grant not yet built in the CRM, etc.) is
    logged at WARNING and never breaks the submission — so the app deploys
    safely ahead of the CRM build (same pattern as the CIntakeSubmission log).
    Self-contained: the request fields are duplicated here for reporting, with
    ``contact`` (and ``infoRequestCompany`` → Account) links back to the
    canonical records.
    """
    payload: dict = {
        "name": f"{sub.first_name} {sub.last_name} — {datetime.now(timezone.utc):%Y-%m-%d}",
        "firstName": sub.first_name,
        "lastName": sub.last_name,
        "email": str(sub.email),
        "submitterEmail": str(sub.email),
        "form": FORM_SLUG,
        "message": sub.message.strip(),
        "description": _submission_json(sub),
        "requestStatus": REQUEST_STATUS_NEW,
        "contactId": contact_id,
    }
    phone = e164_or_none(sub.phone)  # omit an implausible phone rather than 400
    if phone:
        payload["phone"] = phone
    if sub.company:
        payload["company"] = sub.company
    if sub.how_did_you_hear:
        payload["source"] = sub.how_did_you_hear
    if account_id:
        payload["infoRequestCompanyId"] = account_id  # belongsTo Account link
    try:
        created = await client.create(INFO_REQUEST, payload)
        log.info("created %s %s for contact %s", INFO_REQUEST, created["id"], contact_id)
        return created["id"]
    except Exception as exc:  # noqa: BLE001 — best-effort; never break the submission
        log.warning(
            "%s create failed (best-effort): %s; payload=%s", INFO_REQUEST, exc, payload
        )
        return None


async def submit_request(sub: InfoRequest, client: EspoApi) -> dict[str, str]:
    existing = await client.find_one(
        CONTACT, "emailAddress", str(sub.email), select="id,description"
    )
    if existing:
        contact_id = existing["id"]
        prior = (existing.get("description") or "").rstrip()
        block = _description_block(sub, include_company=True)
        description = f"{prior}\n\n{block}" if prior else block
        await client.update(CONTACT, contact_id, {"description": description})
        log.info("appended info request to existing Contact %s", contact_id)
        account_id = None  # existing contact's account is left untouched (by design)
    else:
        account_id = await _find_or_create_account(sub, client) if sub.company else None
        payload = {
            "firstName": sub.first_name,
            "lastName": sub.last_name,
            "emailAddress": str(sub.email),
            C_CONTACT_TYPE: [PROSPECT],
            "description": _description_block(sub, include_company=False),
        }
        phone = e164_or_none(sub.phone)  # omit an implausible phone rather than 400
        if phone:
            payload["phoneNumber"] = phone
        if account_id:
            payload["accountId"] = account_id
        created = await client.create(CONTACT, payload)
        contact_id = created["id"]

    ids = {"contactId": contact_id}
    if account_id:
        ids["accountId"] = account_id
    # Additive: a dedicated Information Request record linked to the contact, on
    # top of the Contact.description stamp and the generic CIntakeSubmission log.
    info_request_id = await _create_information_request(sub, client, contact_id, account_id)
    if info_request_id:
        ids["informationRequestId"] = info_request_id
    return ids
