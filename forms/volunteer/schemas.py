"""Volunteer / Become-a-Mentor application (SCORE form 6).

Maps to a single Contact (contactType = "Mentor") via the CBM MR-APPLY process.
See score-volunteer-form-6-mapping.md. File upload (resume) is a documented
follow-on and is not part of this schema yet.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, model_validator

from core.forms import BaseSubmission

# Static, presentational list (phone_type has no CRM target field).
PhoneType = Literal["Mobile", "Home", "Work"]
# contact_preference / currently_employed are free strings, NOT Literal copies
# of the CRM enums: their dropdowns are synced from the live CRM (options.js),
# so a hard-coded list here would 422 the whole submission the moment a CRM
# enum gains a value. The orchestrator sanitizes both against the live enum.

# ~5 MB file ≈ 6.8 MB base64; cap a little above that.
MAX_RESUME_B64_CHARS = 7_000_000
ALLOWED_RESUME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


class ResumeUpload(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str
    data_base64: str = Field(min_length=1, max_length=MAX_RESUME_B64_CHARS)

    @model_validator(mode="after")
    def _check_type(self) -> "ResumeUpload":
        if self.content_type not in ALLOWED_RESUME_TYPES:
            raise ValueError(f"unsupported resume type: {self.content_type}")
        return self


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
    contact_preference: Optional[str] = Field(default=None, max_length=100)

    # Motivation & background
    why_volunteer: str = Field(min_length=1)
    work_experience: Optional[str] = None
    resume: Optional[ResumeUpload] = None
    currently_employed: Optional[str] = Field(default=None, max_length=100)
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
