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
AS = {"asUser": "u-kitty", "asName": "Kitty Cat"}
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
    assert c.put("/api/courses/small/items/1.1", json={**AS, "done": True}).json()["saved"] is True
    assert c.put("/api/courses/small/items/cp-1", json={**AS, "answer": " REF-42 "}).json()["saved"]
    assert c.put("/api/courses/small/items/9.9", json={**AS, "done": True}).status_code == 404
    early = c.post("/api/courses/small/complete", json=AS).json()
    assert early["completed"] is False
    assert [s["key"] for s in early["missing"]["steps"]] == ["1.2", "2.1"]
    assert [x["key"] for x in early["missing"]["checkpoints"]] == ["cp-2"]
    assert store.done == []
    # Resumed elsewhere: the saved progress comes back with the page.
    page = c.get("/api/courses/small").json()
    assert set(page["progress"]) == {"1.1", "cp-1"} and page["progress"]["cp-1"]["answer"] == "REF-42"
    assert c.get("/api/courses/mine").json()["courses"][0]["status"]["words"] == "In progress, 2 of 5"
    for key in ("1.2", "2.1"):
        c.put(f"/api/courses/small/items/{key}", json={**AS, "done": True})
    c.put("/api/courses/small/items/cp-2", json={**AS, "answer": "4"})
    done = c.post("/api/courses/small/complete", json=AS).json()
    assert done["completed"] is True and done["completion"]["revision"] == "1.0"
    assert store.done[0]["answers"]["cp-1"]["answer"] == "REF-42"
    assert store.done[0]["user_name"] == "Kitty Cat"
    again = c.post("/api/courses/small/complete", json=AS).json()
    assert again["completed"] is True and len(store.done) == 1
    assert c.get("/api/courses/small").json()["completion"]["revision"] == "1.0"
    assert c.get("/api/courses/small").json()["user"] == {"id": "u-kitty", "name": "Kitty Cat"}


def test_unticking_and_clearing_an_answer(monkeypatch, tmp_path, store):
    c = _client(monkeypatch, tmp_path, user=KITTY)
    c.put("/api/courses/small/items/1.1", json={**AS, "done": True})
    c.put("/api/courses/small/items/cp-1", json={**AS, "answer": "x"})
    assert c.put("/api/courses/small/items/1.1", json={**AS, "done": False}).json()["saved"] is False
    assert c.put("/api/courses/small/items/cp-1", json={**AS, "answer": "   "}).json()["saved"] is False
    assert store.rows == []
    assert c.put("/api/courses/small/items/cp-1", json={**AS, "answer": "x" * 2001}).status_code == 422


def test_a_significant_revision_clears_old_ticks_and_says_so(monkeypatch, tmp_path, store):
    c = _client(monkeypatch, tmp_path, user=KITTY)
    c.put("/api/courses/small/items/1.1", json={**AS, "done": True})
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


def test_a_save_for_another_person_is_refused(monkeypatch, tmp_path, store):
    """Found at stop 1 (11-21-26): the browser signed in to an exercise as
    another login, and the course page's saves went in as that login."""
    c = _client(monkeypatch, tmp_path, user={**JOE, "isAdmin": True})
    r = c.put("/api/courses/small/items/1.1", json={**AS, "done": True})
    assert r.status_code == 409
    assert r.json()["detail"].startswith(
        "This course is Kitty Cat's, but this browser is now signed in as Joe Mentor.")
    assert c.put("/api/courses/small/items/cp-1", json={**AS, "answer": "x"}).status_code == 409
    assert c.post("/api/courses/small/complete", json=AS).status_code == 409
    assert store.rows == [] and store.done == []


def test_a_save_from_an_old_page_is_refused(monkeypatch, tmp_path, store):
    c = _client(monkeypatch, tmp_path, user=KITTY)
    r = c.put("/api/courses/small/items/1.1", json={"done": True})
    assert r.status_code == 409 and "out of date" in r.json()["detail"]
    assert c.post("/api/courses/small/complete").status_code == 409
    assert store.rows == []


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
    for name in ("index.html", "course.html", "report.html"):
        html = (ROOT / "courses" / "frontend" / name).read_text()
        scripts = [line.strip() for line in html.splitlines() if "<script src=" in line]
        assert scripts[0] == '<script src="/shared/busy.js"></script>'
        assert scripts[1] == '<script src="/shared/textsize.js"></script>'
        assert '<meta name="cbm-org" content="{{org}}" />' in html


# --- phase 2: the due rule, the dismissal and the Training button --------------------------

def _due(c, app="assignments"):
    body = c.get(f"/api/courses/mine?app={app}").json()
    return {x["id"]: x["reminder"] for x in body["courses"]}


def test_the_change_log_is_read_by_revision():
    md = COURSE_MD.format(rev="2.0") + "| 1.0 | d | a | First. |\n| 2.0 | d | a | Step 1.2 rewritten. |\n"
    assert render.change_log(md) == {"1.0": "First.", "2.0": "Step 1.2 rewritten."}
    assert render.change_log("# T\n\nno log") == {}


def test_a_course_is_due_until_completed(monkeypatch, tmp_path, store):
    c = _client(monkeypatch, tmp_path, user=KITTY)
    assert _due(c)["small"] == {"due": True, "again": False, "change": ""}
    assert c.get("/api/courses/mine").json()["user"] == {"id": "u-kitty", "name": "Kitty Cat"}
    for key, body in (("1.1", {"done": True}), ("1.2", {"done": True}),
                      ("cp-1", {"answer": "R-1"}), ("2.1", {"done": True}),
                      ("cp-2", {"answer": "9"})):
        assert c.put(f"/api/courses/small/items/{key}", json={**AS, **body}).status_code == 200
    assert c.post("/api/courses/small/complete", json=AS).json()["completed"] is True
    assert _due(c)["small"]["due"] is False


def test_a_draft_is_never_due(monkeypatch, tmp_path, store):
    _write_course(tmp_path, cid="small", rev="0.9")
    c = _client(monkeypatch, tmp_path, user=KITTY, courses=discover(tmp_path))
    assert _due(c)["small"]["due"] is False


def test_dismissing_stops_the_reminder_in_every_application(monkeypatch, tmp_path, store):
    _write_course(tmp_path, cid="small", apps="assignments, mentoradmin")
    admin = {**KITTY, "isAdmin": True}
    c = _client(monkeypatch, tmp_path, user=admin, courses=discover(tmp_path))
    r = c.post("/api/courses/small/dismiss", json=AS)
    assert r.status_code == 200 and r.json()["dismissed"] is True
    assert c.post("/api/courses/small/dismiss", json=AS).status_code == 200
    assert len(store.dismissed) == 1 and store.dismissed[0]["major"] == 1
    assert _due(c, "assignments")["small"]["due"] is False
    assert _due(c, "mentoradmin")["small"]["due"] is False
    # A minor revision keeps the dismissal.
    _write_course(tmp_path, cid="small", rev="1.4", apps="assignments, mentoradmin")
    monkeypatch.setattr(service, "catalog", lambda: discover(tmp_path))
    assert _due(c)["small"]["due"] is False


def test_a_significant_revision_brings_it_back_with_its_change(monkeypatch, tmp_path, store):
    c = _client(monkeypatch, tmp_path, user=KITTY)
    c.post("/api/courses/small/dismiss", json=AS)
    d = _write_course(tmp_path, cid="small", rev="2.0")
    md = d / "small.md"
    md.write_text(md.read_text() + "| 2.0 | d | a | Section 2 is new. |\n", encoding="utf-8")
    monkeypatch.setattr(service, "catalog", lambda: discover(tmp_path))
    assert _due(c)["small"] == {"due": True, "again": True, "change": "Section 2 is new."}
    # The same after a completion at 1.0 rather than a dismissal.
    store.dismissed.clear()
    store.done.append({"id": "x", "user_id": "u-kitty", "user_name": "", "course_id": "small",
                       "revision": "1.3", "answers": {},
                       "completed_at": datetime(2026, 11, 1, tzinfo=timezone.utc)})
    assert _due(c)["small"]["again"] is True


def test_a_dismissal_for_another_person_is_refused(monkeypatch, tmp_path, store):
    c = _client(monkeypatch, tmp_path, user={**JOE, "isAdmin": True})
    assert c.post("/api/courses/small/dismiss", json=AS).status_code == 409
    assert c.post("/api/courses/small/dismiss").status_code == 409
    assert store.dismissed == []


def test_dismissing_is_gated_like_the_course(monkeypatch, tmp_path, store):
    c = _client(monkeypatch, tmp_path, user=JOE)
    r = c.post("/api/courses/small/dismiss", json={"asUser": "u-joe", "asName": "Joe Mentor"})
    assert r.status_code == 404 and store.dismissed == []
    off = _client(monkeypatch, tmp_path, on=False, user=KITTY)
    assert off.post("/api/courses/small/dismiss", json=AS).status_code == 404


#: Each application a course may list, and the page that draws it.
APP_PAGES = {
    "assignments": "assignments/frontend/index.html",
    "mentorsessions": "sessions/frontend/index.html",
    "partnersessions": "sessions/frontend/index.html",
    "sponsorsessions": "sessions/frontend/index.html",
    "mentoradmin": "mentoradmin/frontend/index.html",
    "ambassador": "ambassador/frontend/index.html",
}


def test_every_application_a_course_lists_loads_the_training_button():
    """A course naming an application not in APP_PAGES fails here: add the
    page, load training.js after textsize.js and give its header the slot."""
    for course in discover().values():
        for app in course.applications:
            assert app in APP_PAGES, f"{course.id} lists {app}, which has no page here"
            html = (ROOT / APP_PAGES[app]).read_text()
            scripts = [line.strip() for line in html.splitlines() if "<script src=" in line]
            assert scripts[:3] == ['<script src="/shared/busy.js"></script>',
                                   '<script src="/shared/textsize.js"></script>',
                                   '<script src="/shared/training.js"></script>'], app
            head = html[html.index("<header"):html.index("</header>")]
            assert "data-training-slot" in head, app


def test_the_reminder_test_course_can_come_due():
    course = discover()["reminder-test"]
    assert not course.draft and course.changes.get(course.revision)
    assert set(course.applications) == {"assignments", "mentorsessions", "mentoradmin"}


def test_the_training_script_draws_nothing_it_was_not_told_to():
    js = (ROOT / "frontend" / "shared" / "training.js").read_text()
    assert "/api/courses/mine?app=" in js and "/dismiss" in js and "asUser" in js
    assert "disabled" not in js and "position: fixed" not in js
    css = (ROOT / "frontend" / "shared" / "training.css").read_text()
    assert "position: fixed" not in css and "position:fixed" not in css


# --- phase 3: the training report (TR5, § 5.4, decision 10) ------------------------------

MARY = {"userId": "u-mary", "userName": "mary", "name": "Mary Admin", "token": "t",
        "teams": ["Mentor Administration Team"]}

MEMBERS = [
    {"id": "u-kitty", "name": "Kitty Cat", "userName": "kitty", "teams": ["Client Administration Team"]},
    {"id": "u-joe", "name": "Joe Mentor", "userName": "joe", "teams": ["Mentor Team"]},
    {"id": "u-mary", "name": "Mary Admin", "userName": "mary", "teams": ["Mentor Administration Team"]},
    {"id": "u-sue", "name": "Sue Ops", "userName": "sue", "teams": ["Marketing Admin Team"]},
    {"id": "u-ann", "name": "Ann Root", "userName": "ann", "teams": ["Board"], "isAdmin": True},
    {"id": "u-trainee", "name": "Trainee Admin", "userName": "kitty.t",
     "teams": ["Client Administration Team"]},
]


def _report_client(monkeypatch, tmp_path, user=MARY, members=MEMBERS, **kw):
    _write_course(tmp_path, cid="small", apps="assignments, mentorsessions")
    c = _client(monkeypatch, tmp_path, user=user, courses=discover(tmp_path), **kw)

    async def fake_members(settings):
        return [dict(m) for m in members]

    monkeypatch.setattr("courses.router._members", fake_members)
    return c


def _people(c, course="small"):
    r = c.get(f"/api/courses/report/people?course={course}")
    assert r.status_code == 200, r.text
    return r.json()


def test_the_report_gate_is_its_own_setting(monkeypatch, tmp_path, store):
    from core.settings_registry import SETTINGS

    spec = next(s for s in SETTINGS if s.key == "training_report_allowed_teams")
    assert spec.kind == "csv"
    c = _report_client(monkeypatch, tmp_path, user=KITTY)
    r = c.get("/api/courses/report/courses")
    assert r.status_code == 403 and "Mentor Administration Team" in r.json()["detail"]
    assert c.get("/api/courses/mine").json()["reportAllowed"] is False
    c = _report_client(monkeypatch, tmp_path, user={**KITTY, "isAdmin": True})
    assert c.get("/api/courses/report/courses").status_code == 200
    c = _report_client(monkeypatch, tmp_path, user=MARY)
    assert [x["id"] for x in c.get("/api/courses/report/courses").json()["courses"]] == ["small"]
    assert c.get("/api/courses/mine").json()["reportAllowed"] is True


def test_the_report_is_off_with_the_switch(monkeypatch, tmp_path, store):
    c = _report_client(monkeypatch, tmp_path, on=False)
    assert c.get("/api/courses/report/courses").status_code == 404
    assert c.get("/courses/report").status_code == 404


def test_the_report_page_is_its_own_page(monkeypatch, tmp_path, store):
    c = _report_client(monkeypatch, tmp_path)
    html = c.get("/courses/report").text
    assert "Training report" in html and "/courses/assets/report.js" in html
    js = (ROOT / "courses" / "frontend" / "assets" / "report.js").read_text()
    assert "CBMGrid.enhance" in js and "CBMSplit.attach" in js and "disabled" not in js


def test_who_is_listed_follows_decision_10(monkeypatch, tmp_path, store):
    c = _report_client(monkeypatch, tmp_path)
    names = [p["name"] for p in _people(c)["people"]]
    # Kitty (Client Administration) and Joe (Client Management) open the
    # course's applications; Ann is an administrator in a team; Mary's
    # Mentor Administration and Sue's Submission Admin are not the course's.
    # The training sign-in kitty.t is left out by name.
    assert names == ["Ann Root", "Joe Mentor", "Kitty Cat"]


def test_each_status_and_the_counts(monkeypatch, tmp_path, store):
    run = asyncio.run
    c = _report_client(monkeypatch, tmp_path)
    run(store.save_item("u-joe", "small", "1.0", "1.1"))
    run(store.dismiss("u-kitty", "small", 1))
    run(store.complete("u-ann", "Ann Root", "small", "1.0", {}))
    by = {p["name"]: p for p in _people(c)["people"]}
    assert by["Joe Mentor"]["words"] == "In progress, 1 of 5"
    assert by["Kitty Cat"]["words"] == "Dismissed"
    assert by["Ann Root"]["state"] == "completed"
    assert by["Ann Root"]["words"].startswith("Completed 1.0 on ")
    assert by["Ann Root"]["last"] and by["Ann Root"]["lastAt"]
    assert _people(c)["counts"] == {"completed": 1, "due_again": 0, "in_progress": 1,
                                   "dismissed": 1, "not_started": 0}


def test_due_again_after_a_significant_revision(monkeypatch, tmp_path, store):
    run = asyncio.run
    run(store.dismiss("u-kitty", "small", 1))
    run(store.complete("u-joe", "Joe Mentor", "small", "1.0", {}))
    _write_course(tmp_path, cid="small", rev="2.0", apps="assignments, mentorsessions")
    c = _client(monkeypatch, tmp_path, user=MARY, courses=discover(tmp_path))

    async def fake_members(settings):
        return MEMBERS

    monkeypatch.setattr("courses.router._members", fake_members)
    by = {p["name"]: p["words"] for p in _people(c)["people"]}
    assert by["Kitty Cat"] == "Due again" and by["Joe Mentor"] == "Due again"


def test_a_completion_stays_after_the_person_leaves(monkeypatch, tmp_path, store):
    asyncio.run(store.complete("u-gone", "Gone Person", "small", "1.0", {}))
    asyncio.run(store.save_item("u-sue", "small", "1.0", "1.1"))   # no completion: not listed
    c = _report_client(monkeypatch, tmp_path)
    by = {p["name"]: p for p in _people(c)["people"]}
    assert by["Gone Person"]["note"] == "No longer takes this course"
    assert by["Gone Person"]["state"] == "completed"
    assert "Sue Ops" not in by


def test_a_persons_answers(monkeypatch, tmp_path, store):
    c = _report_client(monkeypatch, tmp_path)
    asyncio.run(store.save_item("u-joe", "small", "1.0", "cp-1", "R-1"))
    d = c.get("/api/courses/report/answers?course=small&user=u-joe").json()
    assert d["completions"] == []
    got = {a["key"]: a["answer"] for a in d["current"]["answers"]}
    assert got == {"cp-1": "R-1", "cp-2": ""}
    asyncio.run(store.complete("u-joe", "Joe Mentor", "small", "1.0",
                               {"cp-1": {"question": "Q1", "section": "1. One", "answer": "R-1"}}))
    d = c.get("/api/courses/report/answers?course=small&user=u-joe").json()
    assert d["current"] is None
    assert d["completions"][0]["revision"] == "1.0"
    assert d["completions"][0]["answers"][0]["answer"] == "R-1"
    assert c.get("/api/courses/report/answers?course=nope&user=u-joe").status_code == 404


def test_the_download_is_the_statuses_never_the_answers(monkeypatch, tmp_path, store):
    run = asyncio.run
    members = MEMBERS + [{"id": "u-eve", "name": "=HYPERLINK(1)", "userName": "eve",
                          "teams": ["Mentor Team"]}]
    c = _report_client(monkeypatch, tmp_path, members=members)
    run(store.complete("u-ann", "Ann Root", "small", "1.0",
                       {"cp-1": {"question": "Q1", "section": "1", "answer": "SECRET ANSWER"}}))
    r = c.get("/api/courses/report/download?course=small")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert 'filename="training-small-' in r.headers["content-disposition"]
    text = r.text
    assert text.splitlines()[0] == "Name,Teams,Status,Revision completed,Completed on,Last activity,Note"
    assert "SECRET ANSWER" not in text
    assert "'=HYPERLINK(1)" in text
    r = c.get("/api/courses/report/download?course=small&state=completed")
    assert [line.split(",")[0] for line in r.text.splitlines()[1:]] == ["Ann Root"]
    c = _report_client(monkeypatch, tmp_path, user=KITTY)
    assert c.get("/api/courses/report/download?course=small").status_code == 403
