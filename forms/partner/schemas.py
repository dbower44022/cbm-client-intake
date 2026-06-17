"""Partner application payload — the become-a-partner wizard field set.

An organization applying to partner with CBM. Captures the partner company,
the applicant contact, and how the partnership would work (type + what the
partner can offer). Maps to Account + Contact + CPartnerProfile.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import EmailStr, Field, field_validator

from core.forms import BaseSubmission

# http(s):// + a host containing a dot and no whitespace (e.g. example.com).
# Used to drop non-URL website input that EspoCRM's url field would reject.
_PLAUSIBLE_URL = re.compile(r"^https?://[^\s/]+\.[^\s/]+", re.IGNORECASE)

# Aligned to CPartnerProfile.partnershipType (enum) on the deployed instance.
PartnershipType = Literal[
    "Referral Partner",
    "Training Partner",
    "Cohort",
    "Service Partner",
    "Funding Partner",
    "Community Partner",
]


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
    partnership_type: Optional[PartnershipType] = None
    # Free-form passthrough; the frontend list is aligned to the CRM multiEnum
    # (CPartnerProfile.partnershipValue), like the volunteer form's checkgrids.
    partnership_value: list[str] = Field(default_factory=list)
    how_did_you_hear: Optional[str] = Field(default=None, max_length=255)

    # submission_token + company_url (honeypot) are inherited from BaseSubmission.

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
