"""The postcard landing page's response — the sixth form kind (build plan § 4).

Registered as a form so it rides durable capture, idempotency by submission
token, the near-duplicate hold scoped by the card's token, retries, resumable
delivery and Submission Admin. The landing page at ``/p/{token}`` is its door:
it posts to ``POST /api/campaigns/landing/{token}``, a thin alias over the same
pipeline that takes the token from the URL.
"""

from core.forms import FormSpec

from .orchestrator import orchestrate
from .schemas import ProspectResponse

SPEC = FormSpec(
    slug="prospect-response",
    title="Prospect Response",
    submission_model=ProspectResponse,
    orchestrator=orchestrate,
    frontend_dir=None,  # the landing page is served at /p/{token}
    # Two responses from one card in a day are one person editing one reply; a
    # response from a second card the same day is a second business.
    duplicate_scope_key="scan_token",
    # A same-named company at a different web address holds the row for
    # Submission Admin exactly as the three company-creating forms do.
    company_keys=("business_name", "website"),
)

__all__ = ["SPEC", "ProspectResponse", "orchestrate"]
