"""Operations jobs — the maintenance work that used to need a container console.

Ruling 7: **a mutating job is dry-run first, then apply that exact plan.** This
is the house script convention (``--write`` / ``--apply``) rendered as a UI, and
it is enforced mechanically:

1. the dry-run runs and its output is stored with a **fingerprint**;
2. the apply call names that dry-run. Before changing anything it re-derives the
   plan and compares fingerprints. If the world moved underneath — someone else
   ran a repair, the CRM changed — the apply is **refused** and you review the
   new plan instead. Same stale-write discipline as the assign path.

A job that has no dry-run mode is registered but **not runnable**, and says so.
That is deliberate: several existing maintenance routines mutate immediately and
would need a plan-producing pass written before they belong on this page. A
button that quietly skipped the review step would defeat the ruling.

Jobs run as background tasks in the web process and write their status to
``app_job``, so results survive a page reload and every admin sees the same run
(the receipt sweep's manual trigger in Submission Admin already works this way).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import Column, DateTime, Index, String, Table, Text, desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.config import Settings
from core.store import make_async_engine, metadata

log = logging.getLogger("cbm_intake.setup.jobs")

app_job = Table(
    "app_job",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("job_key", String(64), nullable=False),
    Column("mode", String(16), nullable=False),
    Column("status", String(16), nullable=False),
    Column("plan_fingerprint", String(64)),
    Column("plan_of", String(36)),
    Column("output", Text),
    Column("error", Text),
    Column("reason", Text),
    Column("actor", String(128)),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Index("ix_app_job_started_at", "started_at"),
)

MODE_DRY_RUN = "dry_run"
MODE_APPLY = "apply"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_REFUSED = "refused"

Runner = Callable[[Settings], Awaitable[str]]


@dataclass(frozen=True)
class JobSpec:
    key: str
    name: str
    description: str
    mutating: bool
    dry_run: Optional[Runner] = None
    apply: Optional[Runner] = None
    unavailable_reason: str = ""

    @property
    def runnable(self) -> bool:
        """A mutating job needs BOTH halves; a read-only job needs one."""
        if self.unavailable_reason:
            return False
        return bool(self.apply if not self.mutating else (self.dry_run and self.apply))


async def _capture(fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> str:
    """Run a print-based routine and capture what it printed.

    Several maintenance routines here are scripts whose report IS their stdout.
    Capturing it keeps one implementation for the CLI and the page rather than
    forking the logic.
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = await fn(*args, **kwargs)
    text = buf.getvalue().strip()
    if not text:
        text = f"(no output) result={result!r}"
    return text


# --- job implementations ----------------------------------------------------

async def _stamp_audit_dry(settings: Settings) -> str:
    from scripts.audit_assignment_stamps import run

    return await _capture(run, False, False)


async def _stamp_audit_apply(settings: Settings) -> str:
    from scripts.audit_assignment_stamps import run

    return await _capture(run, True, False)


async def _attachment_cleanup_dry(settings: Settings) -> str:
    from scripts.cleanup_excluded_attachments import run

    return await _capture(run, False, settings)


async def _attachment_cleanup_apply(settings: Settings) -> str:
    from scripts.cleanup_excluded_attachments import run

    return await _capture(run, True, settings)


async def _analytics_refresh(settings: Settings) -> str:
    from analytics.refresh import refresh_system_metrics

    result = await refresh_system_metrics(settings)
    return f"Analytics metric cache refreshed. {result!r}"


async def _schema_drift(settings: Settings) -> str:
    from core import monitoring

    state: dict[str, Any] = {}
    await monitoring.run_schema_drift_check(settings, state)
    return "Schema-drift check complete. " + (
        "Drift reported — see the alert channel." if state else "No drift detected."
    )


JOBS: tuple[JobSpec, ...] = (
    JobSpec(
        key="stamp_audit",
        name="Assignment-stamp audit and heal",
        description=(
            "Walks every assigned engagement, derives who should be able to see it "
            "from the CRM's own links, and reports the records missing that stamp. "
            "Applying merges the missing users in — merge-only, never removing."
        ),
        mutating=True,
        dry_run=_stamp_audit_dry,
        apply=_stamp_audit_apply,
    ),
    JobSpec(
        key="attachment_cleanup",
        name="Clean up excluded email attachments",
        description=(
            "Finds the documents that inbound mail filed automatically but whose "
            "file type is now on the never-file list — calendar invites and the "
            "like. Applying ARCHIVES them: each file moves to its record folder's "
            "_Archived subfolder and leaves the Documents list. Nothing is "
            "deleted, files a person uploaded are never touched, and any of them "
            "can be restored from the record."
        ),
        mutating=True,
        dry_run=_attachment_cleanup_dry,
        apply=_attachment_cleanup_apply,
    ),
    JobSpec(
        key="analytics_refresh",
        name="Refresh the analytics cache",
        description=(
            "Recomputes the cached system metrics. Touches only the app's own cache "
            "table, so it is safe to run at any time."
        ),
        mutating=False,
        apply=_analytics_refresh,
    ),
    JobSpec(
        key="schema_drift",
        name="CRM schema-drift check",
        description=(
            "Compares the live CRM against the app's schema contract. Read-only; "
            "reports through the normal alert channel."
        ),
        mutating=False,
        apply=_schema_drift,
    ),
    JobSpec(
        key="receipt_sweep",
        name="Intake-receipt reconciliation",
        description=(
            "Compares every stored submission against its CIntakeSubmission receipt "
            "and creates or updates receipts to match."
        ),
        mutating=True,
        unavailable_reason=(
            "This routine writes to the CRM as it goes and has no plan-producing "
            "pass, so it cannot honour dry-run-then-apply yet. Run it from "
            "Submission Admin's manual trigger, or add a dry-run mode first."
        ),
    ),
    JobSpec(
        key="docs_reconcile",
        name="Drive grant reconciliation",
        description=(
            "Re-derives every Drive folder grant from the CRM and corrects drift in "
            "both directions."
        ),
        mutating=True,
        unavailable_reason=(
            "Applies grant changes as it goes with no reviewable plan. Needs a "
            "dry-run mode before it belongs on this page."
        ),
    ),
)

BY_KEY = {j.key: j for j in JOBS}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


class JobStore:
    def __init__(self, database_url: str) -> None:
        self._engine = make_async_engine(database_url)

    async def _write(self, values: dict[str, Any]) -> None:
        stmt = (
            pg_insert(app_job)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["id"],
                set_={k: v for k, v in values.items() if k != "id"},
            )
        )
        async with self._engine.begin() as conn:
            await conn.execute(stmt)

    async def get(self, job_id: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(select(app_job).where(app_job.c.id == job_id))
            ).mappings().first()
        return dict(row) if row else None

    async def recent(self, limit: int = 25) -> list[dict[str, Any]]:
        async with self._engine.begin() as conn:
            rows = (
                await conn.execute(
                    select(app_job).order_by(desc(app_job.c.started_at)).limit(limit)
                )
            ).mappings().all()
        return [dict(r) for r in rows]

    async def start(
        self, spec: JobSpec, mode: str, *, actor: str, reason: str, plan_of: str = ""
    ) -> str:
        job_id = str(uuid.uuid4())
        await self._write({
            "id": job_id,
            "job_key": spec.key,
            "mode": mode,
            "status": STATUS_RUNNING,
            "plan_fingerprint": None,
            "plan_of": plan_of or None,
            "output": None,
            "error": None,
            "reason": reason or None,
            "actor": actor or None,
            "started_at": _now(),
            "finished_at": None,
        })
        return job_id

    async def finish(
        self,
        job_id: str,
        spec: JobSpec,
        mode: str,
        *,
        status: str,
        output: str = "",
        error: str = "",
        plan_fingerprint: str = "",
        actor: str = "",
        reason: str = "",
        plan_of: str = "",
    ) -> None:
        await self._write({
            "id": job_id,
            "job_key": spec.key,
            "mode": mode,
            "status": status,
            "plan_fingerprint": plan_fingerprint or None,
            "plan_of": plan_of or None,
            "output": output or None,
            "error": error or None,
            "reason": reason or None,
            "actor": actor or None,
            "started_at": _now(),
            "finished_at": _now(),
        })

    async def dispose(self) -> None:
        await self._engine.dispose()


def make_job_store(settings: Settings) -> Optional[JobStore]:
    if not settings.database_url:
        return None
    return JobStore(settings.database_url)


async def run_dry_run(
    store: JobStore, spec: JobSpec, settings: Settings, *, actor: str, reason: str
) -> dict[str, Any]:
    """Produce the plan. Never changes anything."""
    runner = spec.dry_run or spec.apply
    if runner is None:
        raise ValueError(f"{spec.key} has nothing to run")
    job_id = await store.start(spec, MODE_DRY_RUN, actor=actor, reason=reason)
    try:
        output = await runner(settings)
    except Exception as exc:  # noqa: BLE001 — surfaced on the row, never a 500
        log.warning("job %s dry-run failed: %s", spec.key, exc)
        await store.finish(
            job_id, spec, MODE_DRY_RUN, status=STATUS_FAILED, error=str(exc),
            actor=actor, reason=reason,
        )
        return {"id": job_id, "status": STATUS_FAILED, "error": str(exc)}
    fp = fingerprint(output)
    await store.finish(
        job_id, spec, MODE_DRY_RUN, status=STATUS_DONE, output=output,
        plan_fingerprint=fp, actor=actor, reason=reason,
    )
    return {"id": job_id, "status": STATUS_DONE, "output": output, "fingerprint": fp}


async def run_apply(
    store: JobStore,
    spec: JobSpec,
    settings: Settings,
    *,
    plan_id: str,
    actor: str,
    reason: str,
) -> dict[str, Any]:
    """Apply the reviewed plan — after proving it is still the plan.

    For a mutating job the dry-run is re-derived and its fingerprint compared to
    the one the admin reviewed. A mismatch means the world moved, so nothing is
    applied and the fresh plan is returned for review.
    """
    if spec.apply is None:
        raise ValueError(f"{spec.key} cannot be applied")

    if spec.mutating:
        plan = await store.get(plan_id) if plan_id else None
        if plan is None or plan["job_key"] != spec.key or plan["mode"] != MODE_DRY_RUN:
            return {
                "status": STATUS_REFUSED,
                "error": "Run the dry-run first and apply that plan.",
            }
        if plan["status"] != STATUS_DONE:
            return {"status": STATUS_REFUSED, "error": "That dry-run did not complete."}
        job_id = await store.start(
            spec, MODE_APPLY, actor=actor, reason=reason, plan_of=plan_id
        )
        try:
            current = await (spec.dry_run or spec.apply)(settings)
        except Exception as exc:  # noqa: BLE001
            await store.finish(
                job_id, spec, MODE_APPLY, status=STATUS_FAILED, error=str(exc),
                actor=actor, reason=reason, plan_of=plan_id,
            )
            return {"id": job_id, "status": STATUS_FAILED, "error": str(exc)}
        if fingerprint(current) != (plan["plan_fingerprint"] or ""):
            await store.finish(
                job_id, spec, MODE_APPLY, status=STATUS_REFUSED, output=current,
                error="The plan changed since you reviewed it — nothing was applied.",
                actor=actor, reason=reason, plan_of=plan_id,
            )
            return {
                "id": job_id,
                "status": STATUS_REFUSED,
                "error": "The plan changed since you reviewed it — nothing was "
                         "applied. Review the new plan below and apply that.",
                "output": current,
            }
    else:
        job_id = await store.start(spec, MODE_APPLY, actor=actor, reason=reason)

    try:
        output = await spec.apply(settings)
    except Exception as exc:  # noqa: BLE001
        log.warning("job %s apply failed: %s", spec.key, exc)
        await store.finish(
            job_id, spec, MODE_APPLY, status=STATUS_FAILED, error=str(exc),
            actor=actor, reason=reason, plan_of=plan_id,
        )
        return {"id": job_id, "status": STATUS_FAILED, "error": str(exc)}
    await store.finish(
        job_id, spec, MODE_APPLY, status=STATUS_DONE, output=output,
        actor=actor, reason=reason, plan_of=plan_id,
    )
    return {"id": job_id, "status": STATUS_DONE, "output": output}


def catalogue() -> list[dict[str, Any]]:
    return [
        {
            "key": j.key,
            "name": j.name,
            "description": j.description,
            "mutating": j.mutating,
            "runnable": j.runnable,
            "twoStep": j.mutating and j.runnable,
            "unavailableReason": j.unavailable_reason,
        }
        for j in JOBS
    ]


def job_row(row: dict[str, Any]) -> dict[str, Any]:
    spec = BY_KEY.get(row["job_key"])
    return {
        "id": row["id"],
        "key": row["job_key"],
        "name": spec.name if spec else row["job_key"],
        "mode": row["mode"],
        "status": row["status"],
        "output": row["output"] or "",
        "error": row["error"] or "",
        "reason": row["reason"] or "",
        "actor": row["actor"] or "",
        "startedAt": row["started_at"].isoformat() if row["started_at"] else None,
        "finishedAt": row["finished_at"].isoformat() if row["finished_at"] else None,
        "fingerprint": row["plan_fingerprint"] or "",
        "planOf": row["plan_of"] or "",
    }


# Kept so a future move to worker dispatch has an obvious seam: today jobs run
# in-process as background tasks, which is fine for the routines above (minutes
# at most) and matches the existing manual receipt-sweep trigger.
async def run_in_background(coro: Awaitable[Any]) -> None:
    task = asyncio.create_task(coro)  # noqa: RUF006 — fire-and-forget by design
    task.add_done_callback(
        lambda t: t.exception() and log.warning("background job error: %s", t.exception())
    )
