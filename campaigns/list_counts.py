"""Every list's stored counts, kept current (build plan § 7e.14, ruling 131).

A list's numbers — its people, how many each channel reaches, how many reach
nobody — and each member's reach are stored on the list, so the Lists view
reads them without calling the CRM. They are taken in two places:

- ``refresh_one``: *Refresh* on a list (the web), and one list of the pass.
  A dynamic list is run first, so its members are today's; a static list's
  members are its hand rows.
- ``run_pass``: the worker, every ``CAMPAIGN_LIST_COUNT_SECONDS`` (a day).
  Every active list, one after another; a list that fails is logged and
  the pass goes on.

A campaign already under way keeps the list version it recorded (ruling
64), so re-running a dynamic list here never changes what a signed-off
campaign sends to.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from core.config import Settings
from core.espo import EspoApi

from . import audience
from .audience_store import KIND_DYNAMIC, KIND_STATIC, SOURCE_HAND, STATE_IN, STATUS_ACTIVE

log = logging.getLogger("cbm_intake.campaigns.list_counts")

#: Who the pass records as having run a dynamic list.
PASS_ACTOR = "nightly count"


def member_keys(row: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    """The members the grid shows: a static list's hand rows, a dynamic
    list's last run."""
    if row["kind"] == KIND_STATIC:
        return [r["target_key"] for r in rows if r.get("state") == STATE_IN and r.get("source") == SOURCE_HAND]
    return [r["target_key"] for r in rows if r.get("state") == STATE_IN]


async def refresh_one(client: EspoApi, store, row: dict[str, Any], cat: dict[str, Any], *,
                      actor: str) -> dict[str, Any]:
    """Run a dynamic list, then count either kind and store the result.
    Returns ``{"run": <the run, or None for a static list>, "counts": …}``.
    Raises ``AudienceError`` / ``EspoError`` for the caller to word."""
    run: Optional[dict[str, Any]] = None
    if row["kind"] == KIND_DYNAMIC:
        recipe = audience.normalise_recipe(row["recipe"])
        result = await audience.run_recipe(client, recipe, cat, store=store, _seen=(row["id"],))
        run = {"groups": result["groups"], "included": result["included"], "leftOut": result["leftOut"],
               "total": result["total"], "version": row["version"], "include": recipe["include"]}
        await store.replace_recipe_members(row["id"], result["keys"], run=run, actor=actor)
    keys = member_keys(row, await store.member_rows(row["id"]))
    counted = await audience.count_list(client, keys)
    await store.record_counts(row["id"], counted["counts"], counted["reach"])
    return {"run": run, "counts": counted["counts"]}


def _client(settings: Settings) -> Optional[EspoApi]:
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    from core.espo import EspoClient
    return EspoClient(settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds)


async def run_pass(settings: Settings, *, store, client: Optional[EspoApi] = None) -> dict[str, Any]:
    """The worker's pass over every active list, under the org-wide key.
    The worker passes its own store (one per process). Never raises; returns
    a summary for the log line."""
    summary: dict[str, Any] = {"lists": 0, "counted": 0, "failed": [], "seconds": 0.0}
    if not (settings.campaigns_enabled and settings.campaign_lists) or store is None:
        return summary
    client = client or _client(settings)
    if client is None:
        return summary
    started = time.monotonic()
    try:
        cat = await audience.catalogue(client, settings)
        rows = await store.active_lists()
    except Exception as exc:  # noqa: BLE001 — a pass failure is a log line, never a crash
        log.warning("list count pass: could not start: %s", exc)
        summary["failed"].append(f"start: {exc}")
        return summary
    for row in rows:
        if row.get("status") != STATUS_ACTIVE:
            continue
        summary["lists"] += 1
        try:
            await refresh_one(client, store, row, cat, actor=PASS_ACTOR)
            summary["counted"] += 1
        except Exception as exc:  # noqa: BLE001 — one list failing never stops the rest
            log.warning("list count pass: \"%s\" (%s) not counted: %s", row.get("name"), row["id"], exc)
            summary["failed"].append(row.get("name") or row["id"])
    summary["seconds"] = round(time.monotonic() - started, 1)
    return summary
