"""Request-for-information form.

Creates a Contact (cContactType = "Prospect") with the visitor's question in
the description, plus an Account (cClientStatus = "Prospect") when a company
name is given.
"""

from __future__ import annotations

from pathlib import Path

from core.forms import FormSpec

from .orchestrator import submit_request
from .schemas import InfoRequest

SPEC = FormSpec(
    slug="info-request",
    title="Request Information",
    submission_model=InfoRequest,
    orchestrator=submit_request,
    frontend_dir=Path(__file__).resolve().parent / "frontend",
)
