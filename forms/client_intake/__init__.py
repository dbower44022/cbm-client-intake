"""Client Intake form (SCORE form 111 reconciled to the CBM model).

Creates three linked records: Account + Contact + Engagement.
"""

from __future__ import annotations

from pathlib import Path

from core.forms import FormSpec

from .orchestrator import submit_intake
from .schemas import IntakeSubmission

async def _intake_survey(settings, submission, ids, client):
    """Business Evaluation phase 6 (BE24): email the intake survey. Dark
    behind INTAKE_SURVEY; best-effort; one link per engagement."""
    from evaluation.intake import on_delivered

    await on_delivered(settings, submission, ids, client)


SPEC = FormSpec(
    slug="client-intake",
    title="Request a Mentor",
    submission_model=IntakeSubmission,
    orchestrator=submit_intake,
    frontend_dir=Path(__file__).resolve().parent / "frontend",
    company_keys=("business_name", "business_website"),
    after_delivery=_intake_survey,
)
