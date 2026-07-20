"""Inbound info@ email -> the info-request CRM mapping (Contact, optional
Account, CInformationRequest).

Runs only when staff APPROVE the held submission in /ops (triage-first —
Doug's ruling 2026-07-19: the inbound-requests table + Information Requests
are the single source of truth, but spam must be discardable with zero CRM
residue). Delivery reuses the website form's orchestrator verbatim, with the
email channel's wording and ``source="Email"``; the subject line is folded
into the stored message so staff see it on the Contact and the request.
"""

from __future__ import annotations

from core.espo import EspoApi
from forms.info_request.orchestrator import submit_request

from .schemas import InfoEmail

FORM_SLUG = "info-email"  # value written to CInformationRequest.form
SOURCE = "Email"


async def submit_email(sub: InfoEmail, client: EspoApi) -> dict[str, str]:
    message = sub.message
    if sub.subject:
        message = f"Subject: {sub.subject}\n\n{message}"
    merged = sub.model_copy(update={"message": message})
    channel = f"email to {sub.mailbox}" if sub.mailbox else "email"
    return await submit_request(
        merged, client,
        form_slug=FORM_SLUG, via="email", channel=channel, source=SOURCE,
    )
