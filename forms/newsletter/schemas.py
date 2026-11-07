"""Newsletter signup submission: a name, an address and the consent tick."""

from __future__ import annotations

from typing import Literal

from pydantic import EmailStr, Field

from core.forms import BaseSubmission


class NewsletterSignup(BaseSubmission):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    # The consent IS the signup: a submission without the tick is refused, so
    # nobody is ever put on the list without saying yes (ruling 43).
    marketing_consent: Literal[True]
