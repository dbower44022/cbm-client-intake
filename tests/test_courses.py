"""Training courses, phase 1 (prds/training-app-plan.md § 7): the reader moved
into courses/render.py, the catalogue of course.yaml files, the rules of
status and completion, the routes and pages, and the settings."""

from __future__ import annotations

import asyncio
import pathlib
from datetime import datetime, timezone

import pytest

from courses import catalog as catalog_mod
from courses import render, service
from courses import store as store_mod
from courses.catalog import Course, discover, load_course
from tests.courses_fakes import MemoryCourseStore

ROOT = pathlib.Path(__file__).resolve().parent.parent

COURSE_MD = """# A small course

Last Updated: 11-21-26 10:00 · Revision {rev} — see change log at the end.

Intro text for {{{{org}}}}.

## Before you start

- Sign in: {{{{signin:Client Administration}}}}

## 1. First section

### 1.1 Open the page

- **Where:** Chrome.
- **Action:** paste the address below.

```
{{{{training_url}}}}/client-intake/
```

- **You should see:** the page.

### 1.2 Press the button

- **Action:** press it.

**Checkpoint:** type the reference number shown.

## 2. Second section

### 2.1 Close

- **Action:** close it.

**Checkpoint:** type the score.

## Change log

| Rev | Date | Author | Change |
|---|---|---|---|
"""

YAML = """id: {cid}
title: A small course
minutes: 20
markdown: small.md
applications: [{apps}]
"""


def _write_course(root: pathlib.Path, cid="small", rev="1.0", apps="assignments", folder=None):
    d = root / (folder or cid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "small.md").write_text(COURSE_MD.format(rev=rev), encoding="utf-8")
    (d / "course.yaml").write_text(YAML.format(cid=cid, apps=apps), encoding="utf-8")
    return d


# --- the reader --------------------------------------------------------------------------

def test_items_are_steps_and_checkpoints_in_order(tmp_path):
    course = load_course(_write_course(tmp_path))
    assert [(i["key"], i["kind"]) for i in course.items] == [
        ("1.1", "step"), ("1.2", "step"), ("cp-1", "checkpoint"),
        ("2.1", "step"), ("cp-2", "checkpoint")]
    assert course.items[2]["label"] == "type the reference number shown."


def test_the_claude_page_prints_role_names_never_a_signin(tmp_path):
    doc = load_course(_write_course(tmp_path)).doc
    page = render.render(doc, "k", sub=render.page_sub("https://train.example/"))
    assert "the Client Administration sign-in (from the trainer)" in page
    assert "https://train.example/client-intake/" in page
    assert "{{signin" not in page and "{{training_url}}" not in page


def test_the_script_uses_the_shared_reader():
    text = (ROOT / "scripts" / "build_runbook.py").read_text(encoding="utf-8")
    assert "from courses.render import" in text
    assert "def parse(" not in text and "def step_html(" not in text


def test_the_script_still_makes_the_page(tmp_path):
    import subprocess
    import sys

    src = _write_course(tmp_path) / "small.md"
    out = tmp_path / "page.html"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_runbook.py"), str(src),
                    "--out", str(out), "--training-url", "https://t.example"], check=True)
    html = out.read_text(encoding="utf-8")
    assert html.count('class="step"') == 3 and "https://t.example/client-intake/" in html


def test_signins_parse_and_fill_the_course_page(tmp_path):
    signins = render.parse_signins(
        "Client Administration | kitty | p|w ;\nMentor|joe|x\nbroken line")
    assert signins["client administration"] == ("Client Administration", "kitty", "p|w")
    assert set(signins) == {"client administration", "mentor"}
    doc = load_course(_write_course(tmp_path)).doc
    html = render.body_html(doc, render.app_sub("https://t.example/", signins))
    assert "<code>kitty</code>" in html and "<code>p|w</code>" in html
    assert "https://t.example/client-intake/" in html
    gone = render.body_html(doc, render.app_sub("", {}))
    assert "the Client Administration sign-in, not yet set" in gone


def test_a_signin_is_escaped(tmp_path):
    doc = load_course(_write_course(tmp_path)).doc
    html = render.body_html(doc, render.app_sub("", render.parse_signins(
        "Client Administration | <b>x</b> | a&b")))
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html and "a&amp;b" in html


def test_each_step_has_a_stable_anchor_for_the_help_button(tmp_path):
    doc = load_course(_write_course(tmp_path)).doc
    html = render.body_html(doc)
    assert 'data-key="1.2" id="step-1.2"' in html
    assert 'class="checkpoint" data-key="cp-2" id="cp-2"' in html


# --- the catalogue -----------------------------------------------------------------------

def test_discover_reads_every_course_and_skips_the_broken(tmp_path, caplog):
    _write_course(tmp_path, cid="one")
    _write_course(tmp_path, cid="one", folder="dupe")
    _write_course(tmp_path, cid="report", folder="reserved")
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "course.yaml").write_text("id: bad\napplications: [assignments]\n")
    (bad / "x.md").write_text("# No revision here\n")
    norev = tmp_path / "norev"
    norev.mkdir()
    (norev / "course.yaml").write_text(": : :\n")
    found = discover(tmp_path)
    assert list(found) == ["one"]


def test_revision_is_read_from_the_markdown_only(tmp_path):
    c = load_course(_write_course(tmp_path, rev="2.4"))
    assert (c.revision, c.major, c.draft) == ("2.4", 2, False)
    d = load_course(_write_course(tmp_path, cid="d", rev="0.3"))
    assert d.draft is True


def test_the_evaluation_demo_is_a_course():
    courses = discover()
    demo = courses["evaluation-demo"]
    assert demo.applications == ("assignments", "mentorsessions", "mentoradmin")
    assert demo.draft and demo.minutes == 90
    assert sum(1 for i in demo.items if i["kind"] == "checkpoint") == 8
    text = demo.markdown.read_text(encoding="utf-8")
    assert "{{training_url}}/client-intake/" in text
    for role in ("Client Administration", "Mentor", "Mentor Administration"):
        assert "{{signin:" + role + "}}" in text
    assert "**Checkpoint:** tell the trainer" not in text
    assert all(i["label"].startswith("type ") for i in demo.items if i["kind"] == "checkpoint")


# --- the rules ---------------------------------------------------------------------------

def _row(key, rev="1.0", answer=None):
    return {"item_key": key, "revision": rev, "answer": answer,
            "done_at": datetime(2026, 11, 21, tzinfo=timezone.utc)}


def test_status_missing_and_stale(tmp_path):
    course = load_course(_write_course(tmp_path, rev="1.2"))
    rows = [_row("1.1"), _row("cp-1", "1.1", "R-1"), _row("2.1", "0.9")]
    assert service.stale_keys(course, rows) == ["2.1"]
    st = service.status(course, rows, [])
    assert st == {"state": "in_progress", "words": "In progress, 2 of 5", "done": 2, "total": 5}
    gaps = service.missing(course, rows)
    assert [s["key"] for s in gaps["steps"]] == ["1.2", "2.1"]
    assert [c["key"] for c in gaps["checkpoints"]] == ["cp-2"]
    done = [{"course_id": "small", "revision": "1.0",
             "completed_at": datetime(2026, 11, 20, tzinfo=timezone.utc)}]
    assert service.status(course, rows, done)["words"] == "Completed 1.0 on 11-20-26"
    old = [{**done[0], "revision": "0.4"}]
    assert service.status(course, [], old)["state"] == "not_started"


def test_a_blank_answer_is_not_an_answer(tmp_path):
    course = load_course(_write_course(tmp_path))
    rows = [_row("cp-1", answer="  ")]
    assert "cp-1" in [c["key"] for c in service.missing(course, rows)["checkpoints"]]


# --- the routes --------------------------------------------------------------------------

KITTY = {"userId": "u-kitty", "userName": "kitty", "name": "Kitty Cat", "token": "t",
         "teams": ["Client Administration Team"]}
JOE = {"userId": "u-joe", "userName": "joe", "name": "Joe Mentor", "token": "t",
       "teams": ["Mentor Team"]}


@pytest.fixture
def store():
    s = MemoryCourseStore()
    store_mod.use(s)
    yield s
    store_mod.use(None)


def _client(monkeypatch, tmp_path, *, on=True, user=None, hidden="", courses=None):
    from fastapi.testclient import TestClient

    from core.app import create_app
    from core.config import get_settings
    from forms import info_request

    monkeypatch.setenv("SESSION_SECRET", "s")
    monkeypatch.setenv("TRAINING_COURSES", "true" if on else "false")
    monkeypatch.setenv("TRAINING_HIDDEN_COURSES", hidden)
    monkeypatch.setenv("TRAINING_SYSTEM_URL", "https://train.example")
    monkeypatch.setenv("TRAINING_SIGNINS", "Client Administration | kitty.t | pw1")
    get_settings.cache_clear()
    if courses is None:
        _write_course(tmp_path, cid="small", apps="assignments")
        _write_course(tmp_path, cid="mentors", apps="mentorsessions")
        courses = discover(tmp_path)
    monkeypatch.setattr(service, "catalog", lambda: courses)
    app = create_app([info_request.SPEC])
    if user is not None:
        monkeypatch.setattr("courses.router.current_user", lambda r: user)
    return TestClient(app)


def test_switched_off_is_404_everywhere(monkeypatch, tmp_path, store):
    c = _client(monkeypatch, tmp_path, on=False, user=KITTY)
    assert c.get("/api/courses/mine").status_code == 404
    assert c.get("/api/courses/small").status_code == 404
    assert c.get("/courses/small").status_code == 404
    assert c.get("/courses/").status_code == 404


def test_pages_are_served_when_on(monkeypatch, tmp_path, store):
    c = _client(monkeypatch, tmp_path, user=KITTY)
    page = c.get("/courses/small")
    assert page.status_code == 200 and "/courses/assets/course.js" in page.text
    assert "{{org}}" not in page.text
    assert c.get("/courses/").status_code == 200
    assert c.get("/courses/assets/course.js").status_code == 200


def test_signed_out_is_401(monkeypatch, tmp_path, store):
    c = _client(monkeypatch, tmp_path)
    assert c.get("/api/courses/mine").status_code == 401
    assert c.get("/api/courses/small").status_code == 401


def test_a_course_of_another_application_is_not_found(monkeypatch, tmp_path, store):
    c = _client(monkeypatch, tmp_path, user=JOE)
    r = c.get("/api/courses/small")
    assert r.status_code == 404 and r.json()["detail"] == "That course was not found."
    assert c.get("/api/courses/nope").json()["detail"] == "That course was not found."
    assert [x["id"] for x in c.get("/api/courses/mine").json()["courses"]] == ["mentors"]


def test_a_hidden_course_is_gone(monkeypatch, tmp_path, store):
    c = _client(monkeypatch, tmp_path, user={**KITTY, "isAdmin": True}, hidden="Small")
    assert c.get("/api/courses/small").status_code == 404
    assert [x["id"] for x in c.get("/api/courses/mine").json()["courses"]] == ["mentors"]


def test_the_list_puts_the_application_first(monkeypatch, tmp_path, store):
    admin = {**KITTY, "isAdmin": True}
    c = _client(monkeypatch, tmp_path, user=admin)
    body = c.get("/api/courses/mine?app=mentorsessions").json()
    assert [(x["id"], x["forApp"]) for x in body["courses"]] == [("mentors", True), ("small", False)]
    assert body["courses"][0]["status"]["words"] == "Not started"


def test_the_course_page_fills_the_tokens(monkeypatch, tmp_path, store):
    c = _client(monkeypatch, tmp_path, user=KITTY)
    body = c.get("/api/courses/small").json()
    assert "<code>kitty.t</code>" in body["html"] and "<code>pw1</code>" in body["html"]
    assert "https://train.example/client-intake/" in body["html"]
    assert "{{" not in body["html"]
    assert body["revision"] == "1.0" and body["draft"] is False
    assert body["completion"] is None and body["progress"] == {}


def test_tick_answer_resume_and_complete(monkeypatch, tmp_path, store):
    c = _client(monkeypatch, tmp_path, user=KITTY)
    assert c.put("/api/courses/small/items/1.1", json={"done": True}).json()["saved"] is True
    assert c.put("/api/courses/small/items/cp-1", json={"answer": " REF-42 "}).json()["saved"]
    assert c.put("/api/courses/small/items/9.9", json={"done": True}).status_code == 404
    early = c.post("/api/courses/small/complete").json()
    assert early["completed"] is False
    assert [s["key"] for s in early["missing"]["steps"]] == ["1.2", "2.1"]
    assert [x["key"] for x in early["missing"]["checkpoints"]] == ["cp-2"]
    assert store.done == []
    # Resumed elsewhere: the saved progress comes back with the page.
    page = c.get("/api/courses/small").json()
    assert set(page["progress"]) == {"1.1", "cp-1"} and page["progress"]["cp-1"]["answer"] == "REF-42"
    assert c.get("/api/courses/mine").json()["courses"][0]["status"]["words"] == "In progress, 2 of 5"
    for key in ("1.2", "2.1"):
        c.put(f"/api/courses/small/items/{key}", json={"done": True})
    c.put("/api/courses/small/items/cp-2", json={"answer": "4"})
    done = c.post("/api/courses/small/complete").json()
    assert done["completed"] is True and done["completion"]["revision"] == "1.0"
    assert store.done[0]["answers"]["cp-1"]["answer"] == "REF-42"
    assert store.done[0]["user_name"] == "Kitty Cat"
    again = c.post("/api/courses/small/complete").json()
    assert again["completed"] is True and len(store.done) == 1
    assert c.get("/api/courses/small").json()["completion"]["revision"] == "1.0"


def test_unticking_and_clearing_an_answer(monkeypatch, tmp_path, store):
    c = _client(monkeypatch, tmp_path, user=KITTY)
    c.put("/api/courses/small/items/1.1", json={"done": True})
    c.put("/api/courses/small/items/cp-1", json={"answer": "x"})
    assert c.put("/api/courses/small/items/1.1", json={"done": False}).json()["saved"] is False
    assert c.put("/api/courses/small/items/cp-1", json={"answer": "   "}).json()["saved"] is False
    assert store.rows == []
    assert c.put("/api/courses/small/items/cp-1", json={"answer": "x" * 2001}).status_code == 422


def test_a_significant_revision_clears_old_ticks_and_says_so(monkeypatch, tmp_path, store):
    c = _client(monkeypatch, tmp_path, user=KITTY)
    c.put("/api/courses/small/items/1.1", json={"done": True})
    store.done.append({"id": "x", "user_id": "u-kitty", "user_name": "", "course_id": "small",
                       "revision": "1.0", "answers": {},
                       "completed_at": datetime(2026, 11, 1, tzinfo=timezone.utc)})
    # A minor revision keeps the ticks and the completion.
    _write_course(tmp_path, cid="small", rev="1.1")
    monkeypatch.setattr(service, "catalog", lambda: discover(tmp_path))
    page = c.get("/api/courses/small").json()
    assert page["notice"] == "" and "1.1" in page["progress"] and page["completion"]
    # A significant one clears them and comes due again.
    _write_course(tmp_path, cid="small", rev="2.0")
    page = c.get("/api/courses/small").json()
    assert "changed significantly" in page["notice"] and page["progress"] == {}
    assert page["completion"] is None and store.rows == []


# --- the settings and the database --------------------------------------------------------

def test_the_signins_are_a_secret_and_the_tables_are_kept():
    from core.sandbox_reset import KEEP_TABLES, RESET_TABLES
    from core.settings_registry import BY_KEY, is_secret

    assert is_secret("training_signins")
    for key in ("training_courses", "training_system_url", "training_signins",
                "training_hidden_courses"):
        assert key in BY_KEY
    tables = {"training_progress", "training_completion", "training_dismissal",
              "training_onboarding_write"}
    assert tables <= KEEP_TABLES and not tables & set(RESET_TABLES)


def test_the_migration_creates_the_four_tables():
    text = (ROOT / "alembic" / "versions" / "0054_training_courses.py").read_text()
    for table in ("training_progress", "training_completion", "training_dismissal",
                  "training_onboarding_write"):
        assert f'"{table}"' in text
    assert 'down_revision = "0053_ambassador_report"' in text


def test_the_pages_follow_the_conventions():
    for name in ("index.html", "course.html"):
        html = (ROOT / "courses" / "frontend" / name).read_text()
        scripts = [line.strip() for line in html.splitlines() if "<script src=" in line]
        assert scripts[0] == '<script src="/shared/busy.js"></script>'
        assert scripts[1] == '<script src="/shared/textsize.js"></script>'
        assert '<meta name="cbm-org" content="{{org}}" />' in html
