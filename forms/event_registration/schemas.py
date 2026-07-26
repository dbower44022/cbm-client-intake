"""Event registration submission.

The fields the live sign-up modal already collects — First Name, Last Name,
Email, Phone, Zip Code and the email-consent checkbox — plus the event's slug,
which the register endpoint fills in from the URL path.

Only ``email`` is genuinely required beyond the event: the current form does not
enforce the rest, and tightening validation here would reject registrations the
existing page happily accepts.
"""

from __future__ import annotations

from typing import Optional

from pydantic import EmailStr, Field

from core.forms import BaseSubmission


class EventRegistration(BaseSubmission):
    #: Which event. Set from the URL by ``POST /api/events/{slug}/register``;
    #: also accepted in the body for the generic intake endpoint.
    event_slug: str = Field(min_length=1, max_length=120)

    first_name: str = Field(min_length=1, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=40)
    zip_code: Optional[str] = Field(default=None, max_length=20)

    #: The modal's "I agree to receive emails about CBM webinars" checkbox.
    #: Recorded on the registration, and — when true — on the Contact as the
    #: marketing opt-in plus the terms/privacy acceptances the other four public
    #: forms capture (D-19). Never written as false: a registrant who does not
    #: opt in simply leaves the Contact's existing preferences alone.
    consent: bool = False
