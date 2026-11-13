"""The setup checklist of each integration (prds/integrations-tab-plan.md § 4;
the mapping Doug approved 11-13-26, phase 4 stopping point 1).

The steps stay written in one place, the deployment guide's step files
(``prds/chapter-network/deployment-guide/steps/stage-*.yaml``), so the page and
the guide cannot disagree. A step joins an integration's checklist through two
keys (steps/README.md):

* ``integration: [zoom]`` — the sub-tabs whose checklist shows it. A step on
  two sub-tabs is one step, ticked once for both.
* ``check.auto: [setting_set:zoom_client_id, …]`` — its automatic checks. All
  must pass for the box to tick itself, and a step with any can never be ticked
  by hand. A step without them is ticked by hand.

Each checklist is framed by two rows built here, not in the guide:

* first, "Decide whether this chapter uses <integration>" — ticks itself once
  the "in use" setting has been deliberately set (saved at /setup, or set in
  the deployment), because the default alone says nobody decided. EspoCRM,
  always in use, has none;
* last, "The integration test passes" — ticks itself from the last stored test.

**Opening the page never calls an outside service.** Every check reads the
settings in force, the application's own database (the last test runs, the
mailing connection, the stored Email Setup) or the step files. A check that
cannot answer reads unknown and says why.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

STEPS_DIR = (Path(__file__).resolve().parents[1] / "prds" / "chapter-network"
             / "deployment-guide" / "steps")

DONE = "done"
OPEN = "open"
UNKNOWN = "unknown"

DECIDE_ID = "decide"
TEST_ID = "test"

#: The automatic check names a step may carry.
CHECK_KINDS = ("setting_set", "test_passed", "mailing_connected")


@dataclass(frozen=True)
class Step:
    id: str
    name: str
    stage: int
    stage_name: str
    integrations: tuple[str, ...]
    auto: tuple[str, ...] = ()
    how: str = ""

    @property
    def manual(self) -> bool:
        return not self.auto


@dataclass
class State:
    """What the checks read: everything comes from this application."""

    settings: Any
    overrides: dict[str, Any] = field(default_factory=dict)
    test_runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    ticks: dict[str, dict[str, Any]] = field(default_factory=dict)
    # True / False when the mailing connection was read; None when it could not be.
    mailing_connected: Optional[bool] = None
    # The settings the stored Email Setup holds (the Google features read it
    # first): setting key -> held there.
    stored_google: dict[str, bool] = field(default_factory=dict)


# --- the step files ------------------------------------------------------------

_cache: dict[str, Any] = {"stamp": None, "steps": ()}


def _stage_number(path: Path) -> int:
    m = re.search(r"stage-(\d+)\.yaml$", path.name)
    return int(m.group(1)) if m else 0


def _order(step_id: str) -> tuple[int, ...]:
    return tuple(int(p) for p in step_id.split(".") if p.isdigit())


def _as_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(v).strip() for v in value if str(v).strip())
    return (str(value).strip(),) if str(value).strip() else ()


def load_steps(directory: Path = STEPS_DIR) -> tuple[Step, ...]:
    """Every step that belongs to an integration, in guide order. Re-read when
    a step file changes; cached otherwise."""
    import yaml

    files = sorted(directory.glob("stage-*.yaml"), key=_stage_number)
    stamp = tuple((f.name, f.stat().st_mtime_ns) for f in files)
    if directory == STEPS_DIR and _cache["stamp"] == stamp:
        return _cache["steps"]
    steps: list[Step] = []
    for path in files:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for raw in data.get("steps") or []:
            integrations = _as_list(raw.get("integration"))
            if not integrations:
                continue
            check = raw.get("check") or {}
            how = check.get("how") if isinstance(check, dict) else ""
            if isinstance(how, list):
                how = " ".join(str(h) for h in how)
            steps.append(Step(
                id=str(raw["id"]),
                name=str(raw.get("name") or "").strip(),
                stage=int(data.get("stage") or _stage_number(path)),
                stage_name=str(data.get("name") or "").strip(),
                integrations=integrations,
                auto=_as_list(check.get("auto") if isinstance(check, dict) else None),
                how=str(how or "").strip(),
            ))
    steps.sort(key=lambda s: _order(s.id))
    out = tuple(steps)
    if directory == STEPS_DIR:
        _cache.update(stamp=stamp, steps=out)
    return out


def steps_for(integration: str, steps: Optional[tuple[Step, ...]] = None) -> list[Step]:
    return [s for s in (steps if steps is not None else load_steps()) if integration in s.integrations]


def step_by_id(step_id: str, steps: Optional[tuple[Step, ...]] = None) -> Optional[Step]:
    for s in steps if steps is not None else load_steps():
        if s.id == step_id:
            return s
    return None


def problems(steps: tuple[Step, ...], integration_keys: set[str], setting_keys: set[str]) -> list[str]:
    """Everything wrong with the keys in the step files: an unknown integration,
    an unknown check kind, a check naming an unknown setting or integration."""
    out = []
    for s in steps:
        for i in s.integrations:
            if i not in integration_keys:
                out.append(f"step {s.id}: unknown integration '{i}'")
        for name in s.auto:
            kind, _, arg = name.partition(":")
            if kind not in CHECK_KINDS:
                out.append(f"step {s.id}: unknown check '{name}'")
            elif kind == "setting_set" and arg not in setting_keys:
                out.append(f"step {s.id}: '{name}' names no setting")
            elif kind == "test_passed" and arg not in integration_keys:
                out.append(f"step {s.id}: '{name}' names no integration")
    return out


# --- the checks ------------------------------------------------------------------

def _label(key: str) -> str:
    from core.settings_registry import BY_KEY

    spec = BY_KEY.get(key)
    return spec.label if spec else key


def _is_set(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return bool(str(value).strip())


def evaluate(name: str, state: State) -> tuple[str, str]:
    """One automatic check: (done | open | unknown, the reason in words)."""
    from integrations.registry import BY_KEY as INTEGRATIONS

    kind, _, arg = name.partition(":")
    if kind == "setting_set":
        value = getattr(state.settings, arg, None)
        if _is_set(value):
            return DONE, f"{_label(arg)} is set."
        if state.stored_google.get(arg):
            return DONE, f"{_label(arg)} is held in the stored Email Setup."
        return OPEN, f"{_label(arg)} is not set."
    if kind == "test_passed":
        integ = INTEGRATIONS.get(arg)
        name_ = integ.name if integ else arg
        run = state.test_runs.get(arg)
        if not run:
            return OPEN, f"The {name_} integration test has not been run yet."
        when = str(run.get("finishedAt") or "")[:16].replace("T", " ")
        if run.get("outcome") == "ok":
            return DONE, f"The {name_} integration test passed ({when} UTC)."
        if run.get("outcome") == "failed":
            return OPEN, f"The last {name_} integration test failed ({when} UTC)."
        return OPEN, f"The last {name_} integration test could not be completed ({when} UTC)."
    if kind == "mailing_connected":
        if state.mailing_connected is None:
            return UNKNOWN, "The mailing connection could not be read from the application's database."
        if state.mailing_connected:
            return DONE, "The mailing service is connected."
        return OPEN, "The mailing service is not connected, or needs re-authorisation."
    return UNKNOWN, f"Unknown check '{name}'."


def _combine(results: list[tuple[str, str]]) -> tuple[str, str]:
    outcomes = {r[0] for r in results}
    if OPEN in outcomes:
        state = OPEN
    elif UNKNOWN in outcomes:
        state = UNKNOWN
    else:
        state = DONE
    reasons = [r[1] for r in results if r[0] == state] or [r[1] for r in results]
    return state, " ".join(reasons)


def decided(integ: Any, state: State) -> bool:
    """The "in use" setting was deliberately set: saved at /setup, or set in
    the deployment's own environment."""
    key = integ.in_use_setting
    return key in state.overrides or key.upper() in os.environ


def build(integ: Any, state: State, steps: Optional[tuple[Step, ...]] = None) -> dict[str, Any]:
    """The checklist of one integration, as the page renders it."""
    from integrations.registry import in_use

    rows: list[dict[str, Any]] = []
    if not integ.always_in_use:
        if decided(integ, state):
            used = in_use(integ, state.settings)
            reason = ("Decided: in use." if used else "Decided: not used by this chapter.")
            st = DONE
        else:
            st, reason = OPEN, ("Not decided yet: the “in use” setting below still has its "
                                "default. Save it, on or off, to record the decision.")
        rows.append({"id": DECIDE_ID, "name": f"Decide whether this chapter uses {integ.name}",
                     "stage": None, "automatic": True, "state": st, "reason": reason,
                     "checks": [], "tick": None})
    for step in steps_for(integ.key, steps):
        row = {"id": step.id, "name": step.name, "stage": step.stage,
               "stageName": step.stage_name, "automatic": not step.manual,
               "how": step.how, "checks": list(step.auto), "tick": None,
               "shared": [i for i in step.integrations if i != integ.key]}
        if step.manual:
            tick = state.ticks.get(step.id)
            row["tick"] = tick if tick and tick.get("ticked") else None
            row["state"] = DONE if row["tick"] else OPEN
            row["reason"] = ""
        else:
            row["state"], row["reason"] = _combine([evaluate(c, state) for c in step.auto])
        rows.append(row)
    st, reason = evaluate(f"test_passed:{integ.key}", state)
    rows.append({"id": TEST_ID, "name": "The integration test passes", "stage": None,
                 "automatic": True, "state": st, "reason": reason, "checks": [], "tick": None})
    done = sum(1 for r in rows if r["state"] == DONE)
    return {"rows": rows, "done": done, "total": len(rows)}
