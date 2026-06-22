"""Per-form modules. Each subpackage exposes a ``SPEC`` (core.forms.FormSpec).

``ALL_SPECS`` / ``SPECS_BY_SLUG`` are the single registry used by the web app
(`main.py`) and the delivery worker (`worker.py`).
"""

from . import client_intake, info_request, partner, sponsor, volunteer

ALL_SPECS = [
    client_intake.SPEC,
    volunteer.SPEC,
    info_request.SPEC,
    partner.SPEC,
    sponsor.SPEC,
]

SPECS_BY_SLUG = {spec.slug: spec for spec in ALL_SPECS}
