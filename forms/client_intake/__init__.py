"""Client Intake form (SCORE form 111 reconciled to the CBM model).

Creates three linked records: Account + Contact + Engagement.
"""

from __future__ import annotations

from pathlib import Path

from core.forms import FormSpec

from .orchestrator import submit_intake
from .schemas import IntakeSubmission

SPEC = FormSpec(
    slug="client-intake",
    title="Request a Mentor",
    submission_model=IntakeSubmission,
    orchestrator=submit_intake,
    frontend_dir=Path(__file__).resolve().parent / "frontend",
)
