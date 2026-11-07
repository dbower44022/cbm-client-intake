"""Newsletter signup (Association ruling 43; prds/chapter-website-plan.md, piece E).

A subscriber lands in the CRM first — a Contact with marketing consent set —
and the existing mailing-list synchronisation passes them to the mailing
service. The applications had no such form before 11-07-26.
"""

from __future__ import annotations

from pathlib import Path

from core.forms import FormSpec

from .orchestrator import submit_signup
from .schemas import NewsletterSignup

SPEC = FormSpec(
    slug="newsletter",
    title="Newsletter Signup",
    submission_model=NewsletterSignup,
    orchestrator=submit_signup,
    frontend_dir=Path(__file__).resolve().parent / "frontend",
    enabled_flag="newsletter_form",
)
