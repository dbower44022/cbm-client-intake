"""The survey engine on its own (surveys/, ruling BE23): a test survey
purpose, registered only here, runs end to end through the engine — open,
consent, save with its first-save step, submit, a refusal and the retry;
a purpose switched off answers as an unknown link; nothing answers while no
switch is on; Business Evaluation's old address redirects; and the engine
imports nothing from any survey purpose."""
from __future__ import annotations

import ast
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import apply_overrides, get_settings
from forms import ALL_SPECS as SPECS
from surveys import registry, service
from surveys.store import new_token
from tests.survey_fakes import MemoryStore

ROOT = Path(__file__).resolve().parents[1]

FEEDBACK = """\
key: feedback
version: 1
title: Event feedback
introduction: Tell us how it went.
sections:
  - title: The event
    questions:
      - id: rating
        label: How useful was it?
        type: scale
        required: true
      - id: comment
        label: Anything else?
        type: long_text
"""


class Refused(Exception):
    pass


class Recorder:
    def __init__(self):
        self.submitted: list[tuple[str, dict]] = []
        self.first_saves: list[str] = []
        self.fail = False


def _purpose(tmp_path: Path, rec: Recorder, *, key="test-feedback", switch="business_evaluation"):
    (tmp_path / "feedback.v1.yaml").write_text(FEEDBACK, encoding="utf-8")

    async def submit(ctx):
        if rec.fail:
            raise Refused("the receiving system is down")
        rec.submitted.append((ctx.link["record_id"], ctx.row["answers"]))

    async def first_save(ctx):
        rec.first_saves.append(ctx.row["survey_key"])

    return registry.SurveyPurpose(
        key=key, switch=switch, link_days="evaluation_link_days",
        retry_seconds="evaluation_retry_seconds", definitions_dir=tmp_path,
        surveys_for=lambda link: ["feedback"],
        page=registry.PageText(title="Event Feedback", consent_intro="<p>We ask about the event.</p>",
                               consent_label="I agree to share my feedback.",
                               list_intro="One short survey.", all_done="Thank you."),
        submit=submit, first_save=first_save, client=lambda app: "the-client",
        retryable=(Refused,))


@pytest.fixture
def world(tmp_path):
    rec = Recorder()
    purpose = registry.register(_purpose(tmp_path, rec))
    get_settings.cache_clear()
    apply_overrides({"business_evaluation": "true"})
    app = create_app(SPECS)
    store = MemoryStore()
    app.state.survey_store = store
    link = asyncio.run(store.create_link(
        purpose=purpose.key, entity_type="CEvent", record_id="EV1", data={},
        display_name="Spring Workshop", created_by="test", days=30,
        surveys=[("feedback", "feedback.v1", None)]))
    yield TestClient(app), store, rec, link, purpose
    registry.unregister(purpose.key)
    apply_overrides({})


def test_a_test_purpose_runs_end_to_end(world):
    client, store, rec, link, purpose = world
    t = link["token"]
    page = client.get(f"/survey/{t}")
    assert page.status_code == 200
    assert "Event Feedback" in page.text and "I agree to share my feedback." in page.text
    assert "[[" not in page.text and "Business Evaluation" not in page.text
    state = client.get(f"/api/survey/{t}").json()
    assert state["displayName"] == "Spring Workshop" and [s["key"] for s in state["surveys"]] == ["feedback"]
    assert "EV1" not in str(state)

    assert client.put(f"/api/survey/{t}/answers/feedback", json={"answers": {"rating": 4}}).status_code == 403
    assert client.post(f"/api/survey/{t}/consent", json={"consent": True}).status_code == 200
    for _ in range(2):
        assert client.put(f"/api/survey/{t}/answers/feedback",
                          json={"answers": {"rating": 4}}).json()["state"] == "in_progress"
    assert rec.first_saves == ["feedback"]

    rec.fail = True
    res = client.post(f"/api/survey/{t}/submit/feedback",
                      json={"answers": {"rating": 4, "comment": "Good"}, "submission_token": "s1"})
    assert res.json() == {"state": "submitted", "delivered": False}
    row = store._row(link["id"], "feedback")
    assert "down" in row["delivery_error"] and rec.submitted == []

    row["next_attempt_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    rec.fail = False
    assert asyncio.run(service.run_retry_cycle(store, purpose, "the-client")) == {
        "written": 1, "refused": 0}
    assert rec.submitted == [("EV1", {"rating": 4, "comment": "Good"})]


def test_the_retry_leaves_another_purposes_rows_alone(world, tmp_path):
    _client, store, rec, link, purpose = world
    other = registry.register(_purpose(tmp_path, Recorder(), key="other-purpose"))
    try:
        row = store._row(link["id"], "feedback")
        row.update(submitted_at=datetime.now(timezone.utc), answers={"rating": 3},
                   next_attempt_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        assert asyncio.run(service.run_retry_cycle(store, other, None)) == {"written": 0, "refused": 0}
        assert asyncio.run(service.run_retry_cycle(store, purpose, None))["written"] == 1
    finally:
        registry.unregister(other.key)


def test_a_purpose_switched_off_answers_as_an_unknown_link(tmp_path):
    rec = Recorder()
    purpose = registry.register(_purpose(tmp_path, rec, key="dark-purpose", switch="no_such_switch"))
    try:
        get_settings.cache_clear()
        apply_overrides({"business_evaluation": "true"})
        app = create_app(SPECS)
        store = MemoryStore()
        app.state.survey_store = store
        link = asyncio.run(store.create_link(
            purpose=purpose.key, entity_type="CEvent", record_id="EV1", data={},
            display_name="Spring Workshop", created_by="t", days=30,
            surveys=[("feedback", "feedback.v1", None)]))
        client = TestClient(app)
        for token in (link["token"], new_token()):
            page = client.get(f"/survey/{token}")
            assert page.status_code == 404 and "This link is no longer valid" in page.text
            assert client.get(f"/api/survey/{token}").json() == {"detail": "This link is no longer valid."}
    finally:
        registry.unregister(purpose.key)
        apply_overrides({})


def test_with_no_switch_on_every_survey_address_answers_404():
    get_settings.cache_clear()
    apply_overrides({})
    client = TestClient(create_app(SPECS))
    token = new_token()
    for path in (f"/survey/{token}", f"/api/survey/{token}", "/survey-assets/app.js",
                 f"/evaluation/{token}"):
        res = client.get(path, follow_redirects=False)
        assert res.status_code == 404 and res.json() == {"detail": "Not Found"}


def test_the_old_address_redirects_permanently():
    get_settings.cache_clear()
    apply_overrides({"business_evaluation": "true"})
    try:
        client = TestClient(create_app(SPECS))
        token = new_token()
        res = client.get(f"/evaluation/{token}", follow_redirects=False)
        assert res.status_code == 301 and res.headers["location"] == f"/survey/{token}"
        # The old API is gone.
        assert client.get(f"/api/evaluation/{token}").status_code == 404
        assert client.get("/evaluation-assets/app.js").status_code == 404
    finally:
        apply_overrides({})


def test_the_engine_imports_nothing_from_a_survey_purpose():
    """Ruling BE23: everything specific to a purpose lives in its own package."""
    purposes = {"evaluation"}
    for path in sorted((ROOT / "surveys").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                assert name.split(".")[0] not in purposes, f"{path.name} imports {name}"
    for path in sorted((ROOT / "surveys" / "frontend").iterdir()):
        text = path.read_text(encoding="utf-8")
        assert "/evaluation" not in text, path.name
        if path.name == "invalid.html":
            # The one page no purpose can own: an unknown link has none, and
            # a wording per purpose would tell a caller the link exists. It
            # keeps phase 1's words (Doug's option A, 11-13-26).
            continue
        assert "Business Evaluation" not in text, path.name
