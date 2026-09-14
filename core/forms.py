"""Form registry types.

A form is a self-contained module that contributes a ``FormSpec`` to the app.
The shared core owns the HTTP surface, validation envelope (honeypot +
idempotency token), and the EspoCRM machinery; each form owns only its
submission schema, its EspoCRM mapping (the orchestrator), and — optionally —
a static frontend directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Optional

from pydantic import BaseModel, Field

from .espo import EspoApi


class BaseSubmission(BaseModel):
    """Fields every form submission carries, consumed by the core handler."""

    # Client-generated idempotency token (Technical Design §4.2).
    submission_token: str = Field(min_length=8, max_length=100)
    # Honeypot anti-spam field — real users never see or fill it.
    company_url: str = ""


# An orchestrator turns a validated submission into created EspoCRM record ids.
Orchestrator = Callable[[BaseSubmission, EspoApi], Awaitable[dict]]


@dataclass(frozen=True)
class FormSpec:
    slug: str
    title: str
    submission_model: type[BaseSubmission]
    orchestrator: Orchestrator
    # None for API-only forms whose UI has not been built yet.
    frontend_dir: Optional[Path] = None
    # A second payload key that joins the near-duplicate match, or None.
    #
    # The guard holds a second submission of the same form from the same email
    # inside the hold window, for staff review. That is right for client intake,
    # where re-filling the form is one person EDITING one application. It is
    # wrong wherever a person legitimately submits the same form twice about
    # different things — event registration, where two sign-ups on one day are
    # two different sessions and exactly the behaviour we want to encourage.
    #
    # Naming a key here makes the match form + email + that key, so a repeat for
    # the SAME thing still holds and a repeat for a different one delivers.
    duplicate_scope_key: Optional[str] = None
