"""Intake submission payload — the four-step wizard field set.

Mirrors Requirements Specification §5 (Contact / Account / Engagement field
groups). Required-ness here is the form-layer requirement, which may be
stricter than the underlying canonical field constraint.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import EmailStr, Field, model_validator

from core.forms import BaseSubmission

BusinessStage = Literal[
    "Pre-Startup", "Startup", "Early Stage", "Growth Stage", "Established"
]
MeetingPreference = Literal["No Preference", "Video", "Phone", "Email", "In Person"]
NotificationPreference = Literal["Email", "Text Message"]


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
    meeting_preference: Optional[MeetingPreference] = None
    notification_preference: Optional[NotificationPreference] = None

    # --- Step 3: Your Business (-> Account). All optional even when shown,
    # per Requirements Specification §5.2; business_stage is the branch trigger. ---
    business_stage: BusinessStage
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

    @model_validator(mode="after")
    def _cross_field(self) -> "IntakeSubmission":
        if self.email.lower() != self.confirm_email.lower():
            raise ValueError("email and confirm_email must match")
        if not self.terms_accepted:
            raise ValueError("terms_accepted must be true")
        return self
