"""Event registration — the public webinar sign-up.

Registered as a form kind so it inherits the V2 pipeline wholesale: durable
capture before any external call, idempotency by submission token, retries with
backoff, resumable delivery, and visibility in Submission Admin when something
goes wrong. The website posts to ``POST /api/events/{slug}/register``, which is
a thin alias over the same pipeline.
"""

from core.forms import FormSpec

from .orchestrator import orchestrate
from .schemas import EventRegistration

SPEC = FormSpec(
    slug="event-registration",
    title="Event Registration",
    submission_model=EventRegistration,
    orchestrator=orchestrate,
    frontend_dir=None,  # the form lives on the CBM WordPress site
)

__all__ = ["SPEC", "EventRegistration", "orchestrate"]
