"""Volunteer / Become-a-Mentor form (SCORE form 6, MR-APPLY).

Creates a single Contact (contactType = "Mentor"), with optional resume upload.
"""

from __future__ import annotations

from pathlib import Path

from core.forms import FormSpec

from .orchestrator import submit_application
from .schemas import VolunteerApplication

SPEC = FormSpec(
    slug="volunteer",
    title="Volunteer / Become a Mentor",
    submission_model=VolunteerApplication,
    orchestrator=submit_application,
    frontend_dir=Path(__file__).resolve().parent / "frontend",
)
