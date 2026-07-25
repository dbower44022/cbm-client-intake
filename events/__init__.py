"""Events & Webinars.

Public calendar, registration, Zoom sync, attendance, and the staff admin app —
backed by the CRM's ``CEvent`` / ``CEventRegistration`` entities.

Specs: ``prds/events/CBM_Events_PRD.md`` (requirements),
``prds/events/CBM_Events_Implementation_Plan.md`` (build plan),
``cevent-entities-crm-handoff.md`` (the CRM schema and the changes applied).

Phase 1 (here): the CRM read/derive layer + the public read API.
"""

from .public import api_router

__all__ = ["api_router"]
