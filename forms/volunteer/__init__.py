"""Volunteer / Become-a-Mentor form (SCORE form 6, MR-APPLY).

Backend registered; the frontend UI is a follow-on (frontend_dir=None), so the
form is reachable at POST /api/volunteer/intake but has no served page yet.
"""

from __future__ import annotations

from core.forms import FormSpec

from .orchestrator import submit_application
from .schemas import VolunteerApplication

SPEC = FormSpec(
    slug="volunteer",
    title="Volunteer / Become a Mentor",
    submission_model=VolunteerApplication,
    orchestrator=submit_application,
    frontend_dir=None,
)
