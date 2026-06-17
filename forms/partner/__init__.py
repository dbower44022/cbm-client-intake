"""Become-a-Partner form.

Creates three linked records for an organization applying to partner with CBM:
Account (cAccountType="Partner") + Contact (cContactType="Partner") +
CPartnerProfile (partnershipStatus="Candidate").
"""

from __future__ import annotations

from pathlib import Path

from core.forms import FormSpec

from .orchestrator import submit_partner
from .schemas import PartnerApplication

SPEC = FormSpec(
    slug="partner",
    title="Become a Partner",
    submission_model=PartnerApplication,
    orchestrator=submit_partner,
    frontend_dir=Path(__file__).resolve().parent / "frontend",
)
