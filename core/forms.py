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
    # Campaign attribution (prds/prospect-marketing/build-plan.md § 3.7, § 5):
    # the campaign id and the link token a public door was opened through, and
    # the prospect record a postcard landing page carried over. Hidden fields on
    # every public form; declared here so capture keeps them (an undeclared key
    # is dropped by model_dump). Phase 1 CAPTURES them; Phase 2 honours them at
    # delivery, so no orchestrator reads them yet.
    campaign_id: Optional[str] = Field(default=None, max_length=32)
    campaign_link: Optional[str] = Field(default=None, max_length=16)
    prospect_id: Optional[str] = Field(default=None, max_length=32)
    # The person's lead code (build plan § 7d.3, rulings 71-74): what a personal
    # link carries instead of a CRM id. ``prospect_id`` stays for one release so
    # a submission captured before the change still delivers.
    lead_code: Optional[str] = Field(default=None, max_length=16)
    # Which website button the visitor pressed (Association ruling 35;
    # prds/chapter-website-plan.md, decision 4.4), such as "mentor-profile" or
    # "home-header". Read from ?placement= by frontend/shared/campaign-link.js
    # and written on the lead. Called "button placement" here because
    # "placement" already names the qualification ladder.
    button_placement: Optional[str] = Field(default=None, max_length=64)


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
    # The payload keys holding the company NAME and its WEBSITE, for forms that
    # find-or-create a Company — ``(name_key, website_key)`` — or None.
    #
    # Submission Admin's resolution of a ``held_company`` row writes a
    # ``delivery_overrides`` entry against these keys: "Same company" blanks
    # the website so the name match reuses the company; "Different company"
    # replaces the name so a new one is created (company-website-hold-plan.md).
    company_keys: Optional[tuple[str, str]] = None
    # A setting that must be true for this form to be public, or None for a
    # form that is always public. Read per request: while it is false the
    # form's page and its intake address answer 404, as if absent. A new
    # public form is built dark this way (prds/chapter-website-plan.md, E).
    enabled_flag: Optional[str] = None
    # A best-effort step run once a submission is delivered, by the worker and
    # by the immediate delivery alike: ``(settings, submission, ids, client)``.
    # It must never raise (``run_after_delivery`` guards it anyway) and a
    # re-driven delivery runs it again, so it must be idempotent. Client
    # intake's emails the intake survey (Business Evaluation phase 6, BE24).
    after_delivery: Optional[Callable[..., Awaitable[object]]] = None


async def run_after_delivery(spec: "FormSpec", settings: object, submission: BaseSubmission,
                             ids: dict, client: EspoApi) -> None:
    """Run a form's after-delivery step, best-effort: it never fails the
    delivery it follows."""
    if spec.after_delivery is None:
        return
    try:
        await spec.after_delivery(settings, submission, ids, client)
    except Exception as exc:  # noqa: BLE001 — never fails a delivered submission
        import logging

        logging.getLogger("cbm_intake.forms").warning(
            "%s after-delivery step failed: %s", spec.slug, exc)
