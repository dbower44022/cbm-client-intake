"""Become-a-Sponsor form.

Creates three linked records for an organization interested in sponsoring CBM:
Account (cAccountType="Donor/Sponsor") + Contact (cContactType="Donor") +
CSponsorProfile (message in description).
"""

from __future__ import annotations

from pathlib import Path

from core.forms import FormSpec

from .orchestrator import submit_sponsor
from .schemas import SponsorApplication

SPEC = FormSpec(
    slug="sponsor",
    title="Become a Sponsor",
    submission_model=SponsorApplication,
    orchestrator=submit_sponsor,
    frontend_dir=Path(__file__).resolve().parent / "frontend",
)
