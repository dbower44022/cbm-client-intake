"""Request-for-information submission.

Deliberately minimal — a low-friction "tell me more" form. The message is the
heart of the submission; business details are left for the follow-up
conversation (or the client-intake form if the prospect converts).
"""

from __future__ import annotations

from typing import Optional

from pydantic import EmailStr, Field

from core.forms import BaseSubmission


class InfoRequest(BaseSubmission):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=40)
    company: Optional[str] = Field(default=None, max_length=255)
    message: str = Field(min_length=1, max_length=10_000)
    how_did_you_hear: Optional[str] = Field(default=None, max_length=255)
