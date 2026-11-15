"""Each integration's steps in the deployment guide (prds/integrations-tab-plan.md
§ 4 and § 10).

The steps stay written in one place, the deployment guide's step files
(``prds/chapter-network/deployment-guide/steps/stage-*.yaml``). A step belongs
to an integration through its ``integration:`` key (steps/README.md), for
example ``integration: [zoom]``. The set-up wizard reads its screens from those
steps (``integrations/wizard.py``), and Ask Claude may read the guide text of
any of them (``integrations/diagnosis.read_guide_step``).

Phase 4 built a setup checklist on this module, with automatic checks named by
a ``check.auto:`` key and hand ticks. The wizard replaced it (ruling W4,
phase 10): the checklist, its ticks and the ``check.auto:`` key are gone, and
only the reading of the step files is kept here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

STEPS_DIR = (Path(__file__).resolve().parents[1] / "prds" / "chapter-network"
             / "deployment-guide" / "steps")


@dataclass(frozen=True)
class Step:
    id: str
    name: str
    stage: int
    stage_name: str
    integrations: tuple[str, ...]


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
            steps.append(Step(
                id=str(raw["id"]),
                name=str(raw.get("name") or "").strip(),
                stage=int(data.get("stage") or _stage_number(path)),
                stage_name=str(data.get("name") or "").strip(),
                integrations=integrations,
            ))
    steps.sort(key=lambda s: _order(s.id))
    out = tuple(steps)
    if directory == STEPS_DIR:
        _cache.update(stamp=stamp, steps=out)
    return out


def steps_for(integration: str, steps: Optional[tuple[Step, ...]] = None) -> list[Step]:
    return [s for s in (steps if steps is not None else load_steps()) if integration in s.integrations]


def problems(steps: tuple[Step, ...], integration_keys: set[str]) -> list[str]:
    """Every ``integration:`` value that names no integration."""
    return [f"step {s.id}: unknown integration '{i}'"
            for s in steps for i in s.integrations if i not in integration_keys]


# --- helpers the wizard shares ------------------------------------------------------

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
