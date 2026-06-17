"""Composition root — wires the registered forms into the shared app.

Run with:  uv run uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

from core.app import create_app
from forms import client_intake, info_request, partner, sponsor, volunteer

app = create_app(
    [
        client_intake.SPEC,
        volunteer.SPEC,
        info_request.SPEC,
        partner.SPEC,
        sponsor.SPEC,
    ]
)
