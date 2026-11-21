"""The rules of the training courses (prds/training-app-plan.md): who may take
a course, a person's status in it, the course page's material, and what
completing it needs. The router calls these; nothing else decides them.

- **Who may take a course** (TR2, TR3): anyone signed in who can open at
  least one of the course's applications, by the portal's own rule
  (``portal.router._apps_for``), so access follows each application's team
  gate with nothing kept by hand. A hidden course (TR8) is nobody's.
- **Status**: completed at the current significant revision (the N of N.M,
  TR4), in progress, or not started. A course at 0.x is a draft (decision 9).
- **Progress across revisions** (decision 6): a minor revision keeps the
  trainee's ticks; ticks made against an earlier significant revision are
  cleared, and the page says so.
- **Completed** (TR1): every step ticked and every checkpoint answered. The
  answers are copied into the completion; they are not marked.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from core import branding
from core.config import Settings

from . import render
from .catalog import Course, catalog, major_of


def courses(settings: Settings) -> dict[str, Course]:
    """The courses this deployment offers: every repository course, less the
    hidden ones (TR8)."""
    hidden = settings.training_hidden_courses_set
    return {cid: c for cid, c in catalog().items() if cid.lower() not in hidden}


def routes_for(user: dict[str, Any], settings: Settings) -> set[str]:
    """The applications (by route) this member can open, by the portal's rule."""
    from portal.router import _apps_for

    out = set()
    for app in _apps_for(user, settings):
        route = (app.get("url") or "").strip("/").split("/")[0]
        if route:
            out.add(route)
    return out


def may_take(course: Course, routes: Iterable[str]) -> bool:
    return bool(set(course.applications) & set(routes))


def _date(dt) -> str:
    return dt.strftime("%m-%d-%y") if dt else ""


def current_completion(course: Course, completions: list[dict[str, Any]]) -> Optional[dict]:
    """The newest completion at the course's current significant revision."""
    rows = [c for c in completions if c["course_id"] == course.id
            and major_of(c["revision"]) == course.major]
    return max(rows, key=lambda c: c["completed_at"]) if rows else None


def live_progress(course: Course, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The progress rows that still count: made at the current significant
    revision, on an item the course still has."""
    keys = {i["key"] for i in course.items}
    return [r for r in rows if major_of(r["revision"]) == course.major and r["item_key"] in keys]


def stale_keys(course: Course, rows: list[dict[str, Any]]) -> list[str]:
    """Items ticked against an earlier significant revision (decision 6)."""
    return [r["item_key"] for r in rows if major_of(r["revision"]) != course.major]


def status(course: Course, rows: list[dict[str, Any]],
           completions: list[dict[str, Any]]) -> dict[str, Any]:
    """One course's status for one member, as the list shows it."""
    total = len(course.items)
    done = len(live_progress(course, rows))
    completion = current_completion(course, completions)
    if completion:
        state = "completed"
        words = f"Completed {completion['revision']} on {_date(completion['completed_at'])}"
    elif done:
        state, words = "in_progress", f"In progress, {done} of {total}"
    else:
        state, words = "not_started", "Not started"
    return {"state": state, "words": words, "done": done, "total": total}


def summary(course: Course, settings: Settings) -> dict[str, Any]:
    return {"id": course.id, "title": branding.render(course.title, settings, branding.MODE_TEXT),
            "minutes": course.minutes, "revision": course.revision, "draft": course.draft,
            "applications": list(course.applications), "url": f"/courses/{course.id}"}


def missing(course: Course, rows: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    """What completing the course still needs: the steps not ticked and the
    checkpoints not answered, in course order (decision 7)."""
    have = {r["item_key"]: r for r in live_progress(course, rows)}
    steps, checkpoints = [], []
    for item in course.items:
        row = have.get(item["key"])
        if item["kind"] == "step" and row is None:
            steps.append({"key": item["key"], "label": item["label"]})
        if item["kind"] == "checkpoint" and not (row and (row.get("answer") or "").strip()):
            checkpoints.append({"key": item["key"], "label": item["section"]})
    return {"steps": steps, "checkpoints": checkpoints}


def answers(course: Course, rows: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """The checkpoint answers to copy into a completion, each with the words
    of its question as they read at this revision."""
    have = {r["item_key"]: r for r in live_progress(course, rows)}
    return {i["key"]: {"question": i["label"], "section": i["section"],
                       "answer": (have.get(i["key"]) or {}).get("answer") or ""}
            for i in course.items if i["kind"] == "checkpoint"}


def page(course: Course, settings: Settings) -> dict[str, Any]:
    """The course's material for the course page: its sections drawn in HTML
    with the tokens filled in (decision 5), and its items in order."""
    sub_tokens = render.app_sub(settings.training_system_url,
                                render.parse_signins(settings.training_signins))

    def sub(text: str) -> str:
        return branding.render(sub_tokens(text), settings, branding.MODE_HTML)

    doc = course.doc
    return {
        **summary(course, settings),
        "heading": branding.render(doc["title"], settings, branding.MODE_TEXT),
        "revisionLine": render.inline(doc["revision"], sub),
        "html": render.body_html(doc, sub),
        "items": [{"key": i["key"], "kind": i["kind"]} for i in course.items],
    }
