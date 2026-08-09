"""System Settings — the admin page that controls this deployment's settings.

Plan and rulings: ``prds/system-settings-plan.md``. The override layer itself
lives in ``core/settings_store.py`` (it has to, since ``core.config`` is what
every other package reads); this package is the page over it.
"""

from .router import peer_router, router as api_router

__all__ = ["api_router", "peer_router"]
