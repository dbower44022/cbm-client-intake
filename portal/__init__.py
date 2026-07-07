"""Authenticated portal — the staff/mentor home page at ``/``.

Single sign-on for all staff apps: one CRM login here puts the user (and their
team names) in the shared staff session; each app then enforces its own team
gate per request. See ``portal/router.py``.
"""

from .router import router as api_router

__all__ = ["api_router"]
