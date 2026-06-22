"""Mentor Admin app (``/mentoradmin``).

A staff tool to browse the mentor roster (same searchable/filterable list as the
assignment tool's "Available Mentors") and open any mentor to review every field
and edit them — change status, capacity, expertise, compliance, etc. Gated to
the **Mentor Administration Team** via the shared EspoCRM team-auth, in its own
session. Edits run as the logged-in user (their token), so EspoCRM enforces
their permissions on CMentorProfile.
"""

from .router import router as api_router

__all__ = ["api_router"]
