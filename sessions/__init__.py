"""Session Management tools — one configurable engine, three domains.

Mentors, Partner Managers, and Sponsor Managers each review the records they own
(engagements / partners / sponsors) and record **meetings** against them as
``CSession`` records. It is one entity with the parent link swapped, so the whole
feature is one engine (:mod:`sessions.service`) driven by a per-domain
:class:`sessions.config.DomainConfig`, mounted at three team-gated routes by
:func:`sessions.router.make_router`.
"""

from __future__ import annotations

from .config import DOMAINS, DomainConfig
from .router import make_router

__all__ = ["DOMAINS", "DomainConfig", "make_router"]
