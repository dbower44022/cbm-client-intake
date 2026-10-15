"""The postcard landing page's response (build plan § 4) — the sixth form kind.

What the page asks for: the business name and the mailing address as printed
on the card, both correctable; the person's name, email, phone and website; two
consent ticks worded for what each permits. ``scan_token`` names the card. No
terms-of-use consent — the page is not an application; the standard forms
collect that when a relationship begins.
"""

from __future__ import annotations

from typing import Optional

from pydantic import EmailStr, Field, field_validator

from core.forms import BaseSubmission

ACTION_INFO = "info"
ACTION_MENTOR = "mentor"
ACTION_UPDATE = "update"
ACTIONS = (ACTION_INFO, ACTION_MENTOR, ACTION_UPDATE)


class ProspectResponse(BaseSubmission):
    scan_token: str = Field(min_length=6, max_length=16)
    action: str = ACTION_UPDATE

    business_name: str = Field(default="", max_length=255)
    mailing_street: str = Field(default="", max_length=255)
    mailing_city: str = Field(default="", max_length=100)
    mailing_state: str = Field(default="", max_length=100)
    mailing_zip: str = Field(default="", max_length=40)

    first_name: str = Field(default="", max_length=100)
    last_name: str = Field(default="", max_length=100)
    email: Optional[EmailStr] = None
    phone: str = Field(default="", max_length=40)
    website: str = Field(default="", max_length=255)

    marketing_consent: bool = False
    sms_consent: bool = False

    @field_validator("action")
    @classmethod
    def _known_action(cls, v: str) -> str:
        v = (v or "").strip().lower()
        return v if v in ACTIONS else ACTION_UPDATE

    @field_validator("scan_token")
    @classmethod
    def _lower_token(cls, v: str) -> str:
        return (v or "").strip().lower()

    @field_validator("email", mode="before")
    @classmethod
    def _empty_email_is_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v
