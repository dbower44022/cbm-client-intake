"""Fix plans (prds/integrations-tab-plan.md § 6.3, § 6.4 and § 7), in the
application's database (migration ``0046_integration_fix_plan``).

One row per diagnosis: the integration, the test it diagnosed, the diagnosis
and its confidence, the steps, the fingerprint, the status, who approved it,
the model, the token use and the cost. A diagnosis that produced no plan is a
row too, so its cost counts against the monthly budget. ``kind`` is ``fix``
now; phase 7's setup plans use ``setup``.

**Approval covers that exact plan** (plan § 2): the fingerprint is taken over
the diagnosis and the steps as written, and applying is refused if it differs.
A step the plan did not contain is never carried out.

Statuses: ``diagnosing`` while the agent works, then ``proposed`` → ``applying`` → ``waiting`` (a manual step) →
``applying`` → ``applied`` (the re-test ran) or ``stopped`` (a step failed);
``superseded`` when a newer diagnosis replaces an unfinished plan;
``no_plan`` when the agent finished without one.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime, Float, Index, String, Table, Text, func, select, update
from sqlalchemy.dialects.postgresql import JSONB

from core.store import metadata, shared_engine

FIX = "fix"
SETUP = "setup"

DIAGNOSING = "diagnosing"
PROPOSED = "proposed"
APPLYING = "applying"
WAITING = "waiting"
APPLIED = "applied"
STOPPED = "stopped"
SUPERSEDED = "superseded"
NO_PLAN = "no_plan"
OPEN_STATUSES = (PROPOSED, APPLYING, WAITING)
DISCARDED = "discarded"

#: The action log's words for this module (core/action_log.py convention).
ACT_DIAGNOSED = "Integration Diagnosed"
ACT_PLAN_APPLIED = "Fix Plan Approved and Applied"
ACT_PLAN_STEP = "Fix Plan Step Confirmed"
ACT_PLAN_DISCARDED = "Fix Plan Discarded"
ACT_SETUP_ASKED = "Setup Plan Written"

SETTING_CHANGE = "setting_change"
SETTING_RESET = "setting_reset"
CODED_ACTION = "coded_action"
MANUAL_STEP = "manual_step"
RETEST = "retest"

integration_fix_plan = Table(
    "integration_fix_plan",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("integration", String(40), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("test_run_id", String(36)),
    Column("status", String(16), nullable=False),
    Column("diagnosis", Text),
    Column("confidence", String(16)),
    Column("steps", JSONB, nullable=False),
    Column("fingerprint", String(64)),
    Column("model", String(64)),
    Column("cost", Float, nullable=False),
    Column("usage", JSONB),
    Column("error", Text),
    Column("created_by", String(128)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("approved_by", String(128)),
    Column("approved_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Index("ix_integration_fix_plan_latest", "integration", "created_at"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def fingerprint(diagnosis: str, steps: list[dict[str, Any]]) -> str:
    """Over what the administrator reads: the diagnosis and each step as
    written, never its progress."""
    body = [{k: v for k, v in s.items() if k not in ("state", "detail", "doneBy", "doneAt")}
            for s in steps]
    raw = json.dumps({"diagnosis": diagnosis, "steps": body}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def public(row: Any) -> dict[str, Any]:
    r = dict(row)

    def iso(v: Any) -> Optional[str]:
        return v.isoformat() if v else None

    return {
        "id": r["id"], "integration": r["integration"], "kind": r["kind"],
        "testRunId": r.get("test_run_id"), "status": r["status"],
        "diagnosis": r.get("diagnosis") or "", "confidence": r.get("confidence") or "",
        "steps": r.get("steps") or [], "fingerprint": r.get("fingerprint") or "",
        "model": r.get("model") or "", "cost": round(float(r.get("cost") or 0), 4),
        "usage": r.get("usage") or {}, "error": r.get("error") or "",
        "createdBy": r.get("created_by") or "", "createdAt": iso(r.get("created_at")),
        "approvedBy": r.get("approved_by") or "", "approvedAt": iso(r.get("approved_at")),
        "finishedAt": iso(r.get("finished_at")),
    }


class FixPlanStore:
    def __init__(self, database_url: str) -> None:
        self._engine = shared_engine(database_url)

    async def create(self, *, integration: str, kind: str = FIX, test_run_id: str = "",
                     status: str, diagnosis: str = "", confidence: str = "",
                     steps: Optional[list[dict[str, Any]]] = None, model: str = "",
                     cost: float = 0.0, usage: Optional[dict[str, Any]] = None,
                     error: str = "", created_by: str = "") -> dict[str, Any]:
        steps = steps or []
        row = {
            "id": str(uuid.uuid4()), "integration": integration, "kind": kind,
            "test_run_id": test_run_id or None, "status": status, "diagnosis": diagnosis,
            "confidence": confidence, "steps": steps,
            "fingerprint": fingerprint(diagnosis, steps) if steps else None,
            "model": model, "cost": float(cost or 0), "usage": usage or {}, "error": error or None,
            "created_by": created_by or None, "created_at": _now(),
            "approved_by": None, "approved_at": None, "finished_at": None,
        }
        t = integration_fix_plan
        async with self._engine.begin() as conn:
            if status in (PROPOSED, DIAGNOSING):
                await conn.execute(update(t).where(
                    t.c.integration == integration, t.c.kind == kind,
                    t.c.status.in_(OPEN_STATUSES)).values(status=SUPERSEDED, finished_at=_now()))
            await conn.execute(t.insert().values(**row))
        return public(row)

    async def get(self, plan_id: str) -> Optional[dict[str, Any]]:
        t = integration_fix_plan
        async with self._engine.begin() as conn:
            row = (await conn.execute(select(t).where(t.c.id == plan_id))).mappings().first()
        return public(row) if row else None

    async def latest(self, integration: str, kind: str = FIX) -> Optional[dict[str, Any]]:
        t = integration_fix_plan
        async with self._engine.begin() as conn:
            row = (await conn.execute(
                select(t).where(t.c.integration == integration, t.c.kind == kind)
                .order_by(t.c.created_at.desc()).limit(1))).mappings().first()
        return public(row) if row else None

    async def latest_all(self, kind: str = FIX) -> dict[str, dict[str, Any]]:
        t = integration_fix_plan
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(t).where(t.c.kind == kind).distinct(t.c.integration)
                .order_by(t.c.integration, t.c.created_at.desc()))).mappings().all()
        return {r["integration"]: public(r) for r in rows}

    async def complete(self, plan_id: str, *, status: str, diagnosis: str = "",
                       confidence: str = "", steps: Optional[list[dict[str, Any]]] = None,
                       model: str = "", cost: float = 0.0, usage: Optional[dict[str, Any]] = None,
                       error: str = "") -> None:
        """A diagnosis has finished: its plan (or why there is none) and its cost."""
        steps = steps or []
        t = integration_fix_plan
        async with self._engine.begin() as conn:
            await conn.execute(update(t).where(t.c.id == plan_id).values(
                status=status, diagnosis=diagnosis, confidence=confidence, steps=steps,
                fingerprint=fingerprint(diagnosis, steps) if steps else None,
                model=model, cost=float(cost or 0), usage=usage or {}, error=error or None,
                finished_at=None if status == PROPOSED else _now()))

    async def update(self, plan_id: str, **values: Any) -> None:
        cols = {"status", "steps", "approved_by", "approved_at", "finished_at", "error"}
        clean = {k: v for k, v in values.items() if k in cols}
        t = integration_fix_plan
        async with self._engine.begin() as conn:
            await conn.execute(update(t).where(t.c.id == plan_id).values(**clean))

    async def spent_this_month(self, *, now: Optional[datetime] = None) -> float:
        now = now or _now()
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        t = integration_fix_plan
        async with self._engine.begin() as conn:
            total = (await conn.execute(
                select(func.coalesce(func.sum(t.c.cost), 0.0)).where(t.c.created_at >= start))).scalar()
        return float(total or 0.0)


def make_fix_plan_store(settings: Any) -> Optional[FixPlanStore]:
    if not getattr(settings, "store_enabled", False):
        return None
    return FixPlanStore(settings.database_url)
