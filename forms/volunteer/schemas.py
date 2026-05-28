"""Volunteer / Become-a-Mentor application (SCORE form 6).

Maps to a single Contact (contactType = "Mentor") via the CBM MR-APPLY process.
See score-volunteer-form-6-mapping.md. File upload (resume) is a documented
follow-on and is not part of this schema yet.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import EmailStr, Field, model_validator

from core.forms import BaseSubmission

PhoneType = Literal["Mobile", "Home", "Work"]
ContactPreference = Literal["Email", "Phone", "Text", "No Preference"]
EmploymentStatus = Literal["Yes, Full-time", "Yes, Part-time", "No"]


class VolunteerApplication(BaseSubmission):
    # Identity & contact
    first_name: str = Field(min_length=1, max_length=100)
    middle_initial: Optional[str] = Field(default=None, max_length=1)
    last_name: str = Field(min_length=1, max_length=100)
    preferred_name: Optional[str] = None
    email: EmailStr
    confirm_email: EmailStr
    street: Optional[str] = None
    zip_code: str = Field(min_length=1, max_length=10)
    phone: str = Field(min_length=1, max_length=40)
    phone_type: Optional[PhoneType] = None
    contact_preference: Optional[ContactPreference] = None

    # Motivation & background
    why_volunteer: str = Field(min_length=1)
    work_experience: Optional[str] = None
    currently_employed: Optional[EmploymentStatus] = None
    linkedin_profile: Optional[str] = None

    # Expertise & matching ("choose up to 6")
    industry_experience: list[str] = Field(default_factory=list, max_length=6)
    areas_of_expertise: list[str] = Field(min_length=1, max_length=6)
    fluent_languages: list[str] = Field(default_factory=list)

    # Referral & compliance
    how_did_you_hear: Optional[str] = None
    felony_conviction: bool = False
    terms_accepted: bool

    @model_validator(mode="after")
    def _cross_field(self) -> "VolunteerApplication":
        if self.email.lower() != self.confirm_email.lower():
            raise ValueError("email and confirm_email must match")
        if not self.terms_accepted:
            raise ValueError("terms_accepted must be true")
        return self
