"""Analytics platform (prds/analytics-app-plan.md) — Phase A.

A metric library (code-registered in Phase A; DB-backed builder in Phase B) →
panels → pages, rendered on the standalone ``/analytics`` app. Importing the
package registers the seeded metrics + the System Analytics page.
"""

from __future__ import annotations

from . import computed  # noqa: F401 — registers operational/computed metrics
from . import dashboard  # noqa: F401 — registers metrics + the seeded system page
from . import records  # noqa: F401 — registers the per-record starter dashboards
from .router import router as api_router
from .store import AnalyticsStore, MemoryAnalyticsStore, make_analytics_store

__all__ = [
    "api_router",
    "AnalyticsStore",
    "MemoryAnalyticsStore",
    "make_analytics_store",
]
