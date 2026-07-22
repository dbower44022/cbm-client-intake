"""Inbound info@ email as a submission kind (delivery-only, v0.110.0).

No public route or frontend: rows are captured by the worker's inbound
mailbox poller (held for staff triage in /ops) and delivered by the worker
when approved. The SPEC is registered in ``forms.SPECS_BY_SLUG`` only —
deliberately NOT in ``ALL_SPECS`` (which the web app mounts as public
endpoints).
"""

from core.forms import FormSpec

from .orchestrator import submit_email
from .schemas import InfoEmail

SPEC = FormSpec(
    slug="info-email",
    title="Email to Cleveland Business Mentors",
    submission_model=InfoEmail,
    orchestrator=submit_email,
    frontend_dir=None,
)
