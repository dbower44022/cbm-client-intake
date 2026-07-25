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

from .builder import builder_spec
from .registry import PAGE_REGISTRY, MetricContext, get_metric
from .service import build_time_range, page_spec_from_row, resolve_metric
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
    # The durable submission store feeds store/computed metrics (Phase D).
    from core.store import make_store

    sub_store = make_store(settings)

    # Metric lookup spanning code-registered + authored (DB) metrics.
    db_specs: dict = {}
    try:
        for row in await store.list_metrics():
            db_specs[row["key"]] = builder_spec(row)
    except Exception as exc:  # noqa: BLE001 — fall back to code metrics only
        log.warning("analytics warm: list_metrics failed: %s", exc)

    def lookup(key):
        return db_specs.get(key) or get_metric(key)

    # System pages = code-seeded + authored.
    pages = list(PAGE_REGISTRY.values())
    try:
        code_keys = set(PAGE_REGISTRY)
        for row in await store.list_pages():
            if row.get("key") not in code_keys:
                pages.append(page_spec_from_row(row))
    except Exception as exc:  # noqa: BLE001
        log.warning("analytics warm: list_pages failed: %s", exc)

    refreshed = 0
    errors = 0
    try:
        for page in pages:
            if page.scope != "system":
                continue
            tr = build_time_range(page.default_range)
            for panel in page.panels:
                spec = lookup(panel.metric_key)
                if spec is None or spec.cache_mode != "cached":
                    continue
                ctx = MetricContext(
                    settings=settings, espo=espo, store=store,
                    submission_store=sub_store, time_range=tr,
                )
                payload = await resolve_metric(spec, ctx, force=True)
                if payload.get("error"):
                    errors += 1
                else:
                    refreshed += 1
    finally:
        await store.dispose()
        if sub_store is not None:
            await sub_store.dispose()
    log.info("analytics warm: %s refreshed, %s errors", refreshed, errors)
    return {"refreshed": refreshed, "errors": errors}
