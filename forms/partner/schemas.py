"""Partner application payload — the become-a-partner wizard field set.

An organization applying to partner with CBM. Captures the partner company,
the applicant contact, and how the partnership would work (type + what the
partner can offer). Maps to Account + Contact + CPartnerProfile.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import EmailStr, Field, field_validator, model_validator

from core.forms import BaseSubmission

# http(s):// + a host containing a dot and no whitespace (e.g. example.com).
# Used to drop non-URL website input that EspoCRM's url field would reject.
_PLAUSIBLE_URL = re.compile(r"^https?://[^\s/]+\.[^\s/]+", re.IGNORECASE)


class PartnerApplication(BaseSubmission):
    # --- Step 1: Your Organization (-> Account) ---
    company: str = Field(min_length=1, max_length=255)
    business_website: Optional[str] = None

    # --- Step 2: Your Contact Info (-> Contact) ---
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=40)

    # --- Step 3: Partnership Details (-> CPartnerProfile) ---
    # Free string, NOT a Literal copy of the CRM enum: the dropdown is synced
    # from the live CRM (options.js), so a hard-coded list here 422s the whole
    # submission the moment the CRM enum gains a value (this happened —
    # "other" was added to partnershipType and every "other" submission
    # failed). The orchestrator sanitizes against the live enum instead.
    partnership_type: Optional[str] = Field(default=None, max_length=100)
    # Free-form passthrough; the frontend list is aligned to the CRM multiEnum
    # (CPartnerProfile.partnershipValue), like the volunteer form's checkgrids.
    partnership_value: list[str] = Field(default_factory=list)
    how_did_you_hear: Optional[str] = Field(default=None, max_length=255)
    # Single consent checkbox: Code of Conduct + Terms of Use + Privacy Policy.
    terms_accepted: bool = False

    # submission_token + company_url (honeypot) are inherited from BaseSubmission.

    @model_validator(mode="after")
    def _require_terms(self) -> "PartnerApplication":
        if not self.terms_accepted:
            raise ValueError("terms_accepted must be true")
        return self

    @field_validator("business_website", mode="after")
    @classmethod
    def _normalize_website(cls, v: Optional[str]) -> Optional[str]:
        """Accept a bare domain and store it as a proper URL, dropping junk.

        The Account.website CRM field is a `url` type; a non-empty value without
        a scheme gets `https://` prepended, and anything that doesn't look like a
        real http(s) host is dropped to None rather than 400-ing the submission
        (same rule as the client-intake form).
        """
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        candidate = v if "://" in v else f"https://{v}"
        if not _PLAUSIBLE_URL.match(candidate):
            return None
        return candidate
