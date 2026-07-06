"""Intake submission payload — the four-step wizard field set.

Mirrors Requirements Specification §5 (Contact / Account / Engagement field
groups). Required-ness here is the form-layer requirement, which may be
stricter than the underlying canonical field constraint.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import EmailStr, Field, field_validator, model_validator

from core.forms import BaseSubmission

# http(s):// + a host containing a dot and no whitespace (e.g. example.com).
# Used to drop non-URL website input that EspoCRM's url field would reject.
_PLAUSIBLE_URL = re.compile(r"^https?://[^\s/]+\.[^\s/]+", re.IGNORECASE)

# business_stage / meeting_preference / notification_preference are free
# strings, NOT Literal copies of the CRM enums: their dropdowns are synced from
# the live CRM (options.js), so a hard-coded list here would 422 the whole
# submission the moment a CRM enum gains a value. The orchestrator sanitizes
# each against the live enum before writing.


class IntakeSubmission(BaseSubmission):
    # --- Step 1: About You (-> Contact) ---
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    confirm_email: EmailStr
    phone: str = Field(min_length=1, max_length=40)
    zip_code: str = Field(min_length=1, max_length=10)
    how_did_you_hear: Optional[str] = None

    # --- Step 2: Your Mentoring Request (-> Engagement) ---
    mentoring_focus_areas: list[str] = Field(min_length=1)
    mentoring_needs_description: str = Field(min_length=1)
    meeting_preference: Optional[str] = Field(default=None, max_length=100)
    notification_preference: Optional[str] = Field(default=None, max_length=100)

    # --- Step 3: Your Business (-> Account). All optional even when shown,
    # per Requirements Specification §5.2; business_stage is the branch trigger. ---
    business_stage: str = Field(min_length=1, max_length=100)
    business_name: Optional[str] = None
    business_website: Optional[str] = None
    industry_sector: Optional[str] = None
    industry_subsector: Optional[str] = None
    year_formed: Optional[int] = Field(default=None, ge=1800, le=2100)
    number_of_employees: Optional[int] = Field(default=None, ge=0)

    # --- Step 4: Review and Submit ---
    marketing_consent: bool = False
    terms_accepted: bool

    # submission_token + company_url (honeypot) are inherited from BaseSubmission.

    @field_validator("business_website", mode="after")
    @classmethod
    def _normalize_website(cls, v: Optional[str]) -> Optional[str]:
        """Accept a bare domain and store it as a proper URL, dropping junk.

        The Account.website CRM field is a `url` type, and asking users to type
        the `https://` scheme is needless friction, so a non-empty value without
        a scheme gets `https://` prepended.

        EspoCRM rejects a value that isn't a valid URL, which would 400 the whole
        submission. Since the website is optional, anything that doesn't look
        like a real http(s) host (e.g. "n/a", "none", text with spaces) is
        dropped to None rather than failing the intake.
        """
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        candidate = v if "://" in v else f"https://{v}"
        # Require http(s) + a dotted, space-free host; otherwise drop it.
        if not _PLAUSIBLE_URL.match(candidate):
            return None
        return candidate

    @model_validator(mode="after")
    def _cross_field(self) -> "IntakeSubmission":
        if self.email.lower() != self.confirm_email.lower():
            raise ValueError("email and confirm_email must match")
        if not self.terms_accepted:
            raise ValueError("terms_accepted must be true")
        return self
