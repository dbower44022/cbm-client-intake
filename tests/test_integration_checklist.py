"""Each integration's steps in the deployment guide (integrations/checklist.py;
prds/integrations-tab-plan.md § 4 and § 10).

Phase 4 built a setup checklist on these steps; the set-up wizard replaced it
in phase 10 (ruling W4), and the ``check.auto`` key went with it. What stays is
tested here: the ``integration:`` key names real integrations, every
integration has steps, the key never changes the rendered guide, and the
rendered guide is current.
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

from core.config import get_settings
from integrations import checklist
from integrations.registry import BY_KEY as INTEGRATIONS

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _renderer():
    spec = importlib.util.spec_from_file_location(
        "render_deployment_guide", ROOT / "scripts" / "render_deployment_guide.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_integration_key_names_a_real_integration():
    assert checklist.problems(checklist.load_steps(), set(INTEGRATIONS)) == []


def test_every_integration_has_steps_from_the_guide():
    for key in INTEGRATIONS:
        assert checklist.steps_for(key), f"{key} has no setup steps"


def test_the_approved_mapping():
    by_id = {s.id: s for s in checklist.load_steps()}
    assert by_id["8.4"].integrations == ("google_workspace", "zoom")
    # Phase 9, the Zoom split: 5.5 is Zoom Meetings, 5.18 Zoom Webinars.
    assert by_id["5.5"].integrations == ("zoom_meetings",)
    assert by_id["5.18"].integrations == ("zoom",)
    assert [s.id for s in checklist.steps_for("twilio")] == ["5.15", "5.16", "11.21"]
    assert "4.1" not in by_id and "4.13" not in by_id


def test_problems_catches_an_unknown_integration():
    bad = (checklist.Step("1.1", "x", 1, "s", ("nope", "zoom")),)
    assert checklist.problems(bad, set(INTEGRATIONS)) == ["step 1.1: unknown integration 'nope'"]


def test_no_step_carries_the_removed_check_auto_key():
    """Removed in phase 10 (Doug's decision 11-15-26): nothing reads it."""
    for stage in _renderer().load():
        for step in stage["steps"]:
            assert "auto" not in (step.get("check") or {}), step["id"]


def test_the_integration_key_never_changes_the_rendered_guide():
    r = _renderer()
    for stage in r.load():
        stripped = copy.deepcopy(stage)
        for step in stripped["steps"]:
            step.pop("integration", None)
        assert r.render_stage(stage) == r.render_stage(stripped), stage["stage"]


def test_the_guide_is_rendered_and_its_information_check_passes():
    r = _renderer()
    stages = r.load()
    assert r.information_check(stages) == []
    for path, text in r.build(stages).items():
        assert path.read_text(encoding="utf-8") == text, f"stale: {path.name}"
