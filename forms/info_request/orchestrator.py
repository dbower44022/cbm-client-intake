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
    account). Find-or-create by name like client-intake. On create it is
    typed **Prospect** (ruling 34, 10-17-26 — the type a business carries
    before any relationship, so the relabel at conversion is one rule for
    every public form) with `cClientStatus` untouched; on a CRM that does not carry
    the Prospect option yet (production until its Sunday slot) the form
    falls back to the old shape, cCompanyType=["Client"] +
    cClientStatus="Prospect". A matched existing Account keeps the types it
    has — an information request is not a relationship, so nothing is
    appended (ruling 34). A lead's converted company is used by id
    before any name match (prospect marketing § 5).
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
from core.branding import abbr

import json
import logging
from datetime import datetime, timezone

from campaigns import attribution as attrib
from campaigns import config as campaign_cfg
from campaigns.attribution import Attribution
from core.crm_upsert import COMPANY_SELECT, create_dropping_invalid
from core.espo import EspoApi
from core.phone import e164_or_none
from core.resumable import run_step_once

from .schemas import InfoRequest

log = logging.getLogger("cbm_intake.orchestrator")

ACCOUNT = "Account"
CONTACT = "Contact"
INFO_REQUEST = "CInformationRequest"  # dedicated entity (see cinformation-request-entity.md)
FORM_SLUG = "info-request"  # value written to CInformationRequest.form

A_COMPANY_TYPE = "cCompanyType"    # multiEnum on Account/Company — the type discriminator
A_CLIENT_STATUS = "cClientStatus"  # enum on Account
C_CONTACT_TYPE = "cContactType"    # multiEnum on Contact
C_SMS_OPT_IN = "cSmsOptIn"         # bool on Contact — texts (ruling 9), true-only

CLIENT = "Client"
PROSPECT = "Prospect"
REQUEST_STATUS_NEW = "New"
#: Ruling 17: an information request lands on Engaged — "asked the chapter
#: for something and gave their details to get it". Advance-only (§ 1.8).
ENGAGED = campaign_cfg.STAGE_ENGAGED


def _description_block(
    sub: InfoRequest, *, include_company: bool, via: str = "website"
) -> str:
    """The stamped, human-readable note staff will read on the Contact."""
    lines = [f"[Information request via {via} — {datetime.now(timezone.utc):%Y-%m-%d}]"]
    if include_company and sub.company:
        lines.append(f"Company: {sub.company}")
    if sub.how_did_you_hear:
        lines.append(f"How they heard about {abbr()}: {sub.how_did_you_hear}")
    lines.append("")
    lines.append(sub.message.strip())
    return "\n".join(lines)


async def _find_or_create_account(
    sub: InfoRequest, client: EspoApi, attr: Attribution | None = None
) -> str:
    """The company the request names, by id from the lead first,
    then by name, else created typed Prospect (ruling 34)."""
    attr = attr or Attribution()
    select = f"{COMPANY_SELECT},{attrib.FUNNEL_STAGE}"
    promoted = await attrib.promoted_company(client, attr, select=select)
    if promoted is not None:
        log.info("using converted Account %s from lead %s", promoted["id"],
                 (attr.prospect or {}).get("id"))
        # The business has now asked for something: Engaged, advance-only.
        if await attrib.rung_available(client, ACCOUNT):
            await attrib.advance_rung(client, ACCOUNT, promoted, ENGAGED)
        return promoted["id"]

    existing = await client.find_one(ACCOUNT, "name", sub.company, select=COMPANY_SELECT)
    if existing:
        log.info("matched existing Account %s for %r", existing["id"], sub.company)
        # Ruling 34: a company the CRM already knows keeps the types it has. An
        # information request is not a relationship, so nothing is appended —
        # a partner that asks a question stays a partner.
        return existing["id"]

    if await attrib.prospect_type_available(client):
        payload: dict = {"name": sub.company, A_COMPANY_TYPE: [PROSPECT]}
        # This submission creates the company: it carries the campaign (ruling
        # 27) and enters the funnel at Engaged (ruling 17, § 1.8).
        stage = ENGAGED if await attrib.rung_available(client, ACCOUNT) else None
        attrib.stamp_new(payload, attr, stage=stage)
    else:
        # The shape this form wrote before ruling 34, kept until the CRM has
        # the Prospect option — EspoCRM refuses an unknown multiEnum value.
        payload = {"name": sub.company, A_COMPANY_TYPE: [CLIENT], A_CLIENT_STATUS: PROSPECT}
    created = await client.create(ACCOUNT, payload)
    return created["id"]


def _submission_json(sub: InfoRequest, *, channel: str = "the website") -> str:
    """The raw submission as a readable note + JSON, for the entity's description
    (mirrors the CIntakeSubmission audit record)."""
    data = json.loads(sub.model_dump_json())
    data["company_url"] = ""            # clear the honeypot field
    data.pop("submission_token", None)  # internal idempotency token, not useful here
    body = json.dumps(data, indent=2, sort_keys=True)
    return (
        f"Information request submitted via {channel}.\n\n"
        "----- submission payload -----\n" + body
    )


async def _create_information_request(
    sub: InfoRequest,
    client: EspoApi,
    contact_id: str,
    account_id: str | None,
    *,
    form_slug: str = FORM_SLUG,
    channel: str = "the website",
    source: str | None = None,
    attr: Attribution | None = None,
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
        "form": form_slug,
        "message": sub.message.strip(),
        "description": _submission_json(sub, channel=channel),
        "requestStatus": REQUEST_STATUS_NEW,
        "contactId": contact_id,
    }
    phone = e164_or_none(sub.phone)  # omit an implausible phone rather than 400
    if phone:
        payload["phone"] = phone
    if sub.company:
        payload["company"] = sub.company
    if source or sub.how_did_you_hear:
        payload["source"] = source or sub.how_did_you_hear
    if account_id:
        payload["infoRequestCompanyId"] = account_id  # belongsTo Account link
    if attr is not None and attr.campaign:
        # The campaign lands on the relationship record every time (ruling 27),
        # with the notes line that says the LINK did it (§ 5 step 8).
        payload[attrib.CAMPAIGN_FK] = attr.campaign["id"]
        payload["description"] = f"{attr.note()}\n\n{payload['description']}"
    try:
        created = await create_dropping_invalid(client, INFO_REQUEST, payload)
        log.info("created %s %s for contact %s", INFO_REQUEST, created["id"], contact_id)
        return created["id"]
    except Exception as exc:  # noqa: BLE001 — best-effort; never break the submission
        log.warning(
            "%s create failed (best-effort): %s; payload=%s", INFO_REQUEST, exc, payload
        )
        return None


async def submit_request(
    sub: InfoRequest,
    client: EspoApi,
    *,
    form_slug: str = FORM_SLUG,
    via: str = "website",
    channel: str = "the website",
    source: str | None = None,
) -> dict[str, str]:
    """Deliver one information request. The keyword args let another channel
    reuse the whole mapping — the info-email kind (inbound info@ mail approved
    in /ops, v0.110.0) passes its own form value, "via email" wording, and
    ``source="Email"``; the defaults keep the website form's exact behavior."""
    # The campaign id and the prospect id the form carried, validated or
    # dropped (prospect marketing § 5 step 1) — never a reason to lose the lead.
    attr = await attrib.resolve(client, sub, entity=INFO_REQUEST)
    existing = await client.find_one(
        CONTACT, "emailAddress", str(sub.email), select=f"id,description,cContactType,{attrib.FUNNEL_STAGE}"
    )
    if existing:
        contact_id = existing["id"]
        # Rung evidence (ruling 17): the person asked for something. Advance-
        # only, best-effort, and only on a CRM that carries the field.
        if await attrib.rung_available(client, CONTACT):
            await attrib.advance_rung(client, CONTACT, existing, ENGAGED)

        # The append ACCUMULATES, so a delivery retry must not re-run it
        # (pipeline-M1: a partial failure after this update used to duplicate
        # the block in staff-visible data on redrive). The named progress step
        # guards it under the worker's / sync path's ResumableClient.
        async def _append() -> None:
            prior = (existing.get("description") or "").rstrip()
            block = _description_block(sub, include_company=True, via=via)
            description = f"{prior}\n\n{block}" if prior else block
            await client.update(CONTACT, contact_id, {"description": description})
            log.info("appended info request to existing Contact %s", contact_id)

        if not await run_step_once(client, f"append-description:{contact_id}", _append):
            log.info("description append already recorded for Contact %s (retry)", contact_id)
        if getattr(sub, "sms_consent", False):
            # True-only, best-effort: the tick is consent, never a reason to lose the request.
            try:
                await client.update(CONTACT, contact_id, {C_SMS_OPT_IN: True})
            except Exception as exc:  # noqa: BLE001
                log.warning("could not record the SMS opt-in on Contact %s: %s", contact_id, exc)
        account_id = None  # existing contact's account is left untouched (by design)
    else:
        account_id = await _find_or_create_account(sub, client, attr) if sub.company else None
        payload = {
            "firstName": sub.first_name,
            "lastName": sub.last_name,
            "emailAddress": str(sub.email),
            C_CONTACT_TYPE: [PROSPECT],
            "description": _description_block(sub, include_company=False, via=via),
        }
        # A NEW contact carries the campaign (ruling 27) and enters the funnel
        # at Engaged (ruling 17) — the entry stage is written once, here.
        stage = ENGAGED if await attrib.rung_available(client, CONTACT) else None
        attrib.stamp_new(payload, attr, stage=stage)
        phone = e164_or_none(sub.phone)  # omit an implausible phone rather than 400
        if phone:
            payload["phoneNumber"] = phone
        if account_id:
            payload["accountId"] = account_id
        if getattr(sub, "sms_consent", False):
            payload[C_SMS_OPT_IN] = True   # true-only (ruling 9)
        created = await create_dropping_invalid(client, CONTACT, payload)
        contact_id = created["id"]

    ids = {"contactId": contact_id}
    if account_id:
        ids["accountId"] = account_id
    # Additive: a dedicated Information Request record linked to the contact, on
    # top of the Contact.description stamp and the generic CIntakeSubmission log.
    info_request_id = await _create_information_request(
        sub, client, contact_id, account_id,
        form_slug=form_slug, channel=channel, source=source, attr=attr,
    )
    if info_request_id:
        ids["informationRequestId"] = info_request_id
    # Ruling 48: the lead the form named is Converted, or a new record gets a
    # lead behind it, Converted at once — Lead Source the form, or Email for
    # an approved info@ message.
    lead_source = campaign_cfg.SOURCE_EMAIL if source == "Email" else campaign_cfg.SOURCE_INFO_REQUEST
    await attrib.record_lead(client, attr, source=lead_source, company_id=account_id,
                             contact_id=contact_id, values=attrib.lead_values(sub))
    ids.update(attr.result())
    return ids
