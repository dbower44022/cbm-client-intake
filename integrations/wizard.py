"""The setup wizard of each integration (prds/integrations-tab-plan.md § 10,
rulings W1 to W6; Zoom's screens approved by Doug 11-14-26).

**The guide chooses the steps** (W2): a step in the deployment guide's step
files carries a ``wizard:`` list of screens, beside its ``actions:``; the
renderer never prints it. A screen is one action (W3) with ``what``, ``why``
and ``how``, and one of:

* ``ask:`` — a question; each answer may ``sets:`` settings and says
  ``then:`` (``next``, ``end``, or a screen id);
* ``enters:`` — a box for one setting, saved through the checked save path;
* neither — a vendor-console action, confirmed with Done.

``check:`` is what proves the screen done: ``decided:<setting>``,
``setting_set:<key>``, ``test:<integration>`` or
``test:<integration>/<check>``; none means Done. ``when:`` (``<screen>=<answer>``)
skips a screen unless an earlier answer matches.

**Where it starts** (W5): at the first screen whose check fails, judged from
the settings and the last stored integration test — opening the wizard never
calls an outside service. A Done screen never fails on its own, so screens
before the first failing one are taken as done. Every check passing: the
integration is set up. A run in progress resumes where it was left.

**Progress** is kept for the whole deployment (one row per integration, in
``integration_wizard``), so a second administrator sees the same place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime, Float, Index, String, Table, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.store import metadata, shared_engine

PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"
END = "end"

integration_wizard = Table(
    "integration_wizard",
    metadata,
    Column("integration", String(40), primary_key=True),
    Column("progress", JSONB, nullable=False),
    Column("updated_by", String(128)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

#: One row per call to Claude from the wizard ("Ask Claude about this"),
#: with its cost: the monthly budget counts them with the diagnoses.
integration_agent_call = Table(
    "integration_agent_call",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("integration", String(40), nullable=False),
    Column("screen", String(64)),
    Column("status", String(16), nullable=False),     # running | answered | failed
    Column("answer", Text),
    Column("cost", Float, nullable=False),
    Column("asked_by", String(128)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_integration_agent_call_month", "created_at"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- the screens ------------------------------------------------------------------------

@dataclass(frozen=True)
class Screen:
    id: str
    step: str
    title: str
    what: str = ""
    why: str = ""
    how: str = ""
    see: str = ""
    if_not: str = ""
    ask: tuple[dict[str, Any], ...] = ()
    enters: str = ""
    check: str = ""
    copy: tuple[str, ...] = ()
    when: str = ""

    @property
    def kind(self) -> str:
        if self.ask:
            return "question"
        if self.enters:
            return "enter"
        return "done"

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "step": self.step, "title": self.title, "what": self.what,
                "why": self.why, "how": self.how, "see": self.see, "ifNot": self.if_not,
                "answers": [str(a.get("answer")) for a in self.ask], "enters": self.enters,
                "check": self.check, "copy": list(self.copy), "kind": self.kind}


_cache: dict[Any, Any] = {}


def screens_for(integration: str, steps_dir: Any = None) -> list[Screen]:
    """Every wizard screen of the integration, in guide order. Re-read when a
    step file changes; cached otherwise."""
    import yaml

    from integrations.checklist import STEPS_DIR, _order, _stage_number

    directory = steps_dir or STEPS_DIR
    files = sorted(directory.glob("stage-*.yaml"), key=_stage_number)
    stamp = (str(directory), integration, tuple((f.name, f.stat().st_mtime_ns) for f in files))
    if stamp in _cache:
        return list(_cache[stamp])
    found: list[tuple[tuple[int, ...], int, Screen]] = []
    for path in files:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for raw in data.get("steps") or []:
            integ = raw.get("integration") or []
            if integration not in (integ if isinstance(integ, list) else [integ]):
                continue
            for n, w in enumerate(raw.get("wizard") or []):
                found.append((_order(str(raw["id"])), n, Screen(
                    id=str(w["id"]), step=str(raw["id"]), title=str(w.get("title") or ""),
                    what=str(w.get("what") or ""), why=str(w.get("why") or ""),
                    how=str(w.get("how") or ""), see=str(w.get("see") or ""),
                    if_not=str(w.get("if_not") or ""), ask=tuple(w.get("ask") or ()),
                    enters=str(w.get("enters") or ""), check=str(w.get("check") or ""),
                    copy=tuple(str(c) for c in (w.get("copy") or ())), when=str(w.get("when") or ""),
                )))
    found.sort(key=lambda x: (x[0], x[1]))
    out = [s for _, _, s in found]
    _cache[stamp] = tuple(out)
    return out


def problems(screens: list[Screen], setting_keys: set[str], integration_keys: set[str]) -> list[str]:
    """Everything wrong with the screens' keys."""
    out, ids = [], {s.id for s in screens}
    if len(ids) != len(screens):
        out.append("two screens share an id")
    for s in screens:
        kind, _, arg = s.check.partition(":")
        if s.check and kind not in ("decided", "setting_set", "test"):
            out.append(f"{s.id}: unknown check '{s.check}'")
        if kind in ("decided", "setting_set") and arg not in setting_keys:
            out.append(f"{s.id}: '{s.check}' names no setting")
        if kind == "test" and arg.split("/")[0] not in integration_keys:
            out.append(f"{s.id}: '{s.check}' names no integration")
        if s.enters and s.enters not in setting_keys:
            out.append(f"{s.id}: enters '{s.enters}', which is no setting")
        for a in s.ask:
            then = str(a.get("then") or "next")
            if then not in ("next", END) and then not in ids:
                out.append(f"{s.id}: answer '{a.get('answer')}' goes to unknown screen '{then}'")
            for key in (a.get("sets") or {}):
                if key not in setting_keys:
                    out.append(f"{s.id}: answer '{a.get('answer')}' sets '{key}', which is no setting")
    return out


# --- the checks ----------------------------------------------------------------------------

@dataclass
class State:
    settings: Any
    overrides: dict[str, Any] = field(default_factory=dict)
    test_runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    answers: dict[str, str] = field(default_factory=dict)


def _set(value: Any) -> bool:
    from integrations.checklist import _is_set

    return _is_set(value)


def evaluate(screen: Screen, state: State) -> tuple[str, str]:
    """(pass | fail | unknown, the reason in words) for one screen's check,
    from what this application already holds."""
    import os

    from integrations.checklist import _label

    if not screen.check:
        return PASS, ""
    kind, _, arg = screen.check.partition(":")
    if kind == "decided":
        if arg in state.overrides or arg.upper() in os.environ or screen.id in state.answers:
            return PASS, "Answered."
        return FAIL, "Not answered yet."
    if kind == "setting_set":
        return (PASS, f"{_label(arg)} is set.") if _set(getattr(state.settings, arg, None)) \
            else (FAIL, f"{_label(arg)} is not set.")
    if kind == "test":
        integ, _, check = arg.partition("/")
        run = state.test_runs.get(integ)
        if not run:
            return FAIL, "The integration test has not been run yet."
        if not check:
            return (PASS, "The integration test passes.") if run.get("outcome") == "ok" \
                else (FAIL, "The integration test does not pass yet.")
        row = next((c for c in run.get("checks") or [] if c.get("key") == check), None)
        if row is None:
            return FAIL, "The integration test did not reach this check."
        if row.get("outcome") == "ok":
            return PASS, str(row.get("detail") or "")
        return FAIL, str(row.get("detail") or row.get("label") or "")
    return UNKNOWN, f"Unknown check '{screen.check}'."


def _applies(screen: Screen, answers: dict[str, str]) -> bool:
    if not screen.when:
        return True
    sid, _, answer = screen.when.partition("=")
    return answers.get(sid) == answer


def start(screens: list[Screen], state: State) -> Optional[str]:
    """The first screen whose check fails (W5), or None: every check passes."""
    for s in screens:
        if not _applies(s, state.answers):
            continue
        if evaluate(s, state)[0] != PASS:
            return s.id
    return None


def next_screen(screens: list[Screen], current: str, answers: dict[str, str],
                then: str = "next") -> Optional[str]:
    """The screen after ``current``, following ``then``; None at the end."""
    if then == END:
        return None
    ids = [s.id for s in screens]
    if then not in ("next", "") and then in ids:
        return then
    i = ids.index(current) + 1 if current in ids else 0
    for s in screens[i:]:
        if _applies(s, answers):
            return s.id
    return None


# --- progress ----------------------------------------------------------------------------------

def blank() -> dict[str, Any]:
    return {"current": None, "history": [], "answers": {}, "done": [], "finished": False,
            "ended": "", "failure": None, "help": None}


class WizardStore:
    def __init__(self, database_url: str) -> None:
        self._engine = shared_engine(database_url)

    async def get(self, integration: str) -> Optional[dict[str, Any]]:
        t = integration_wizard
        async with self._engine.begin() as conn:
            row = (await conn.execute(select(t).where(t.c.integration == integration))).mappings().first()
        return dict(row["progress"]) if row else None

    async def all(self) -> dict[str, dict[str, Any]]:
        t = integration_wizard
        async with self._engine.begin() as conn:
            rows = (await conn.execute(select(t))).mappings().all()
        return {r["integration"]: dict(r["progress"]) for r in rows}

    async def put(self, integration: str, progress: dict[str, Any], *, by: str = "") -> None:
        t = integration_wizard
        stmt = pg_insert(t).values(integration=integration, progress=progress, updated_by=by or None,
                                   updated_at=_now())
        stmt = stmt.on_conflict_do_update(index_elements=[t.c.integration],
                                          set_={"progress": progress, "updated_by": by or None,
                                                "updated_at": _now()})
        async with self._engine.begin() as conn:
            await conn.execute(stmt)

    async def record_call(self, *, call_id: str, integration: str, screen: str, status: str,
                          answer: str = "", cost: float = 0.0, asked_by: str = "") -> None:
        t = integration_agent_call
        values = {"integration": integration, "screen": screen, "status": status, "answer": answer,
                  "cost": float(cost or 0), "asked_by": asked_by or None}
        stmt = pg_insert(t).values(id=call_id, created_at=_now(), **values)
        stmt = stmt.on_conflict_do_update(index_elements=[t.c.id], set_=values)
        async with self._engine.begin() as conn:
            await conn.execute(stmt)

    async def spent_this_month(self, *, now: Optional[datetime] = None) -> float:
        now = now or _now()
        first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        t = integration_agent_call
        async with self._engine.begin() as conn:
            total = (await conn.execute(
                select(func.coalesce(func.sum(t.c.cost), 0.0)).where(t.c.created_at >= first))).scalar()
        return float(total or 0.0)


def make_wizard_store(settings: Any) -> Optional[WizardStore]:
    if not getattr(settings, "store_enabled", False):
        return None
    return WizardStore(settings.database_url)


# --- what the page shows ----------------------------------------------------------------------

def _prefill(screen: Screen, settings: Any) -> dict[str, Any]:
    """The box's current value; a secret only as set or not set."""
    from core.settings_registry import is_secret

    if not screen.enters:
        return {}
    value = getattr(settings, screen.enters, None)
    if is_secret(screen.enters):
        return {"secret": True, "isSet": _set(value), "value": ""}
    return {"secret": False, "isSet": _set(value), "value": "" if value is None else str(value)}


def view(integration: str, settings: Any, overrides: dict[str, Any],
         test_runs: dict[str, dict[str, Any]], progress: Optional[dict[str, Any]],
         screens: Optional[list[Screen]] = None) -> Optional[dict[str, Any]]:
    """The wizard as the page draws it, or None when the integration has no
    screens yet. Never calls an outside service."""
    screens = screens if screens is not None else screens_for(integration)
    if not screens:
        return None
    p = dict(blank(), **(progress or {}))
    state = State(settings=settings, overrides=overrides, test_runs=test_runs, answers=p["answers"])
    ids = [s.id for s in screens]
    current = p["current"] if p["current"] in ids else None
    status = "running"
    if p.get("ended"):
        status, current = "ended", None
    elif p.get("finished"):
        status, current = "done", None
    elif current is None:
        current = start(screens, state)
        if current is None:
            status = "done"
    out: dict[str, Any] = {"status": status, "total": len(screens), "ended": p.get("ended") or "",
                           "canBack": bool(p["history"]), "help": p.get("help")}
    if current:
        screen = screens[ids.index(current)]
        result, reason = evaluate(screen, state)
        out.update(position=ids.index(current) + 1, screen=dict(screen.as_dict(), **_prefill(screen, settings)),
                   failure=p.get("failure") if (p.get("failure") or {}).get("screen") == current else None,
                   checkNow={"result": result, "reason": reason} if screen.check else None)
    return out
