"""Worker job: keep the seeded system dashboard's ``cached`` metrics warm.

Runs on ``analytics_refresh_seconds`` (worker timer). Recomputes every system
page's cached metrics for that page's default range and writes them to the
cache, so the dashboard renders instantly and stays fresh without waiting for a
first viewer. Inert without a store or a real CRM client (dry-run / no API key).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from core.config import Settings
from core.espo import EspoClient

from .registry import PAGE_REGISTRY, MetricContext, get_metric
from .service import build_time_range, resolve_metric
from .store import make_analytics_store

log = logging.getLogger("cbm_intake.analytics")


def system_client(settings: Settings) -> Optional[EspoClient]:
    """The org-wide API-key CRM client for system metrics (None in dry-run)."""
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    return EspoClient(
        settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
    )


async def refresh_system_metrics(settings: Settings) -> dict[str, Any]:
    store = make_analytics_store(settings)
    if store is None:
        return {"refreshed": 0, "reason": "no store"}
    espo = system_client(settings)
    if espo is None:
        await store.dispose()
        return {"refreshed": 0, "reason": "no crm client"}

    refreshed = 0
    errors = 0
    try:
        for page in PAGE_REGISTRY.values():
            if page.scope != "system":
                continue
            tr = build_time_range(page.default_range)
            for panel in page.panels:
                spec = get_metric(panel.metric_key)
                if spec is None or spec.cache_mode != "cached":
                    continue
                ctx = MetricContext(
                    settings=settings, espo=espo, store=store, time_range=tr
                )
                payload = await resolve_metric(spec, ctx, force=True)
                if payload.get("error"):
                    errors += 1
                else:
                    refreshed += 1
    finally:
        await store.dispose()
    log.info("analytics warm: %s refreshed, %s errors", refreshed, errors)
    return {"refreshed": refreshed, "errors": errors}
