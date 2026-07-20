"""An inbound email to the shared info@ mailbox, captured as a submission.

Built by the worker's inbound-mailbox poller (``ops/inbound.py``) — never by
an HTTP POST; this form kind has no public endpoint or frontend. Extends the
website info-request with the email facts (subject + Gmail ids) so the /ops
conversation view can anchor to the originating thread.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from forms.info_request.schemas import InfoRequest


class InfoEmail(InfoRequest):
    subject: Optional[str] = Field(default=None, max_length=500)
    # The Gmail thread/message this submission was captured from (in the
    # shared OPS_MAILBOX). The thread id is the conversation anchor.
    gmail_thread_id: str = Field(default="", max_length=64)
    gmail_message_id: str = Field(default="", max_length=64)
    # The shared mailbox it arrived at (for the audit note wording).
    mailbox: str = Field(default="", max_length=255)
