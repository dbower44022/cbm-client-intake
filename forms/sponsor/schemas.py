"""Sponsor application payload — the become-a-sponsor wizard field set.

An organization interested in sponsoring CBM. Deliberately light: company,
applicant contact, and a free-text message describing their interest. Maps to
Account + Contact + CSponsorProfile; staff fill in the contribution details
later.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import EmailStr, Field, field_validator, model_validator

from core.forms import BaseSubmission

# http(s):// + a host containing a dot and no whitespace (e.g. example.com).
_PLAUSIBLE_URL = re.compile(r"^https?://[^\s/]+\.[^\s/]+", re.IGNORECASE)


class SponsorApplication(BaseSubmission):
    # --- Step 1: Your Organization (-> Account) ---
    company: str = Field(min_length=1, max_length=255)
    business_website: Optional[str] = None

    # --- Step 2: Your Contact Info (-> Contact) ---
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=40)

    # --- Step 3: Your Message (-> CSponsorProfile.description) ---
    message: str = Field(min_length=1, max_length=10_000)
    how_did_you_hear: Optional[str] = Field(default=None, max_length=255)
    # Single consent checkbox: Code of Conduct + Terms of Use + Privacy Policy.
    terms_accepted: bool = False

    # submission_token + company_url (honeypot) are inherited from BaseSubmission.

    @model_validator(mode="after")
    def _require_terms(self) -> "SponsorApplication":
        if not self.terms_accepted:
            raise ValueError("terms_accepted must be true")
        return self

    @field_validator("business_website", mode="after")
    @classmethod
    def _normalize_website(cls, v: Optional[str]) -> Optional[str]:
        """Accept a bare domain and store it as a proper URL, dropping junk.

        Same rule as the client-intake / partner forms: prepend ``https://`` to a
        scheme-less value and drop anything that isn't a plausible http(s) host
        rather than 400-ing the submission on the Account.website url field.
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
