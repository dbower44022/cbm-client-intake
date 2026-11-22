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
- **Due** (plan § 6, phase 2): a course the member can take, not hidden,
  at 1.0 or later, with no completion and no dismissal at the current N.
  Computed, never stored. **Due again** is due after a completion or a
  dismissal at an earlier N, and carries the current revision's change log
  entry (TR4).
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


def dismissed(course: Course, dismissals: list[dict[str, Any]]) -> bool:
    """The member dismissed this course's reminder at its current N."""
    return any(d["course_id"] == course.id and int(d["major"]) == course.major
               for d in dismissals)


def due(course: Course, completions: list[dict[str, Any]],
        dismissals: list[dict[str, Any]]) -> dict[str, Any]:
    """Whether the reminder shows for this course (the caller has already
    checked that the member can take it and that it is not hidden):
    ``{"due", "again", "change"}``. ``change`` is the current revision's
    change log entry, given only when the course is due again."""
    if course.draft or current_completion(course, completions) or dismissed(course, dismissals):
        return {"due": False, "again": False, "change": ""}
    earlier = any(c["course_id"] == course.id and major_of(c["revision"]) < course.major
                  for c in completions) or any(
        d["course_id"] == course.id and int(d["major"]) < course.major for d in dismissals)
    return {"due": True, "again": earlier,
            "change": course.changes.get(course.revision, "") if earlier else ""}


def due_courses(user: dict[str, Any], settings: Settings, completions: list[dict[str, Any]],
                dismissals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every course due for this member, across every application they can
    open: the home page's Needs you rows (TR6, § 5.3) come from here, by the
    same rule as the reminder bar. Each is :func:`summary` plus ``reminder``."""
    routes = routes_for(user, settings)
    out = []
    for course in courses(settings).values():
        if not may_take(course, routes):
            continue
        reminder = due(course, completions, dismissals)
        if reminder["due"]:
            out.append({**summary(course, settings), "reminder": reminder})
    return out


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


# --- the training report (TR5, decision 10, § 5.4; phase 3) ------------------------------

#: The report's statuses, in the order the counts line and the status sort use.
REPORT_STATES = ("completed", "due_again", "in_progress", "dismissed", "not_started")
REPORT_WORDS = {"completed": "completed", "due_again": "due again",
                "in_progress": "in progress", "dismissed": "dismissed",
                "not_started": "not started"}


def signin_usernames(settings: Settings) -> frozenset[str]:
    """The training sign-ins' usernames, left out of the report by name."""
    return frozenset(u.lower() for _, u, _ in render.parse_signins(settings.training_signins).values())


def person_status(course: Course, progress: list[dict[str, Any]],
                  completions: list[dict[str, Any]],
                  dismissals: list[dict[str, Any]]) -> dict[str, Any]:
    """One person's status in one course, as the report shows it. Completed
    at the current N first; then dismissed at the current N (with any
    progress); then in progress; then due again (a completion or a
    dismissal at an earlier N); else not started."""
    total = len(course.items)
    done = len(live_progress(course, progress))
    completion = current_completion(course, completions)
    stamps = ([r["done_at"] for r in progress] + [c["completed_at"] for c in completions]
              + [d["dismissed_at"] for d in dismissals if d["course_id"] == course.id])
    last = max(stamps) if stamps else None
    if completion:
        state = "completed"
        words = f"Completed {completion['revision']} on {_date(completion['completed_at'])}"
    elif dismissed(course, dismissals):
        state, words = "dismissed", "Dismissed" + (f", {done} of {total}" if done else "")
    elif done:
        state, words = "in_progress", f"In progress, {done} of {total}"
    elif any(major_of(c["revision"]) < course.major for c in completions) or any(
            int(d["major"]) < course.major for d in dismissals if d["course_id"] == course.id):
        state, words = "due_again", "Due again"
    else:
        state, words = "not_started", "Not started"
    return {"state": state, "words": words, "last": last,
            "revision": completion["revision"] if completion else "",
            "completedAt": completion["completed_at"] if completion else None}


def report(course: Course, members: list[dict[str, Any]], records: dict[str, list[dict[str, Any]]],
           settings: Settings) -> dict[str, Any]:
    """The report's rows for one course (decision 10). The people are every
    member (news.service.members: active regular logins, and administrators
    in at least one team) who can open one of the course's applications, by
    the portal's rule, less the training sign-ins by username. Someone with a
    completion who no longer takes the course stays, marked, so a completion
    never drops off the record (announced at stop 3a, 11-21-26)."""
    excluded = signin_usernames(settings)
    by_user: dict[str, dict[str, list]] = {}
    for kind in ("progress", "completions", "dismissals"):
        for r in records.get(kind) or []:
            by_user.setdefault(r["user_id"], {"progress": [], "completions": [], "dismissals": []})[kind].append(r)
    known = {m["id"]: m for m in members}
    people: dict[str, dict[str, Any]] = {}
    for m in members:
        if (m.get("userName") or "").lower() in excluded:
            continue
        user = {"teams": m.get("teams") or [], "isAdmin": bool(m.get("isAdmin"))}
        if may_take(course, routes_for(user, settings)):
            people[m["id"]] = {"name": m["name"], "teams": m.get("teams") or [], "counted": True}
    for uid, rec in by_user.items():
        if uid in people or not rec["completions"]:
            continue
        m = known.get(uid)
        if m and (m.get("userName") or "").lower() in excluded:
            continue
        name = (m or {}).get("name") or rec["completions"][0].get("user_name") or "A former member"
        people[uid] = {"name": name, "teams": (m or {}).get("teams") or [], "counted": False}
    rows = []
    empty = {"progress": [], "completions": [], "dismissals": []}
    for uid, p in people.items():
        rec = by_user.get(uid, empty)
        st = person_status(course, rec["progress"], rec["completions"], rec["dismissals"])
        rows.append({
            "userId": uid, "name": p["name"], "teams": p["teams"],
            "state": st["state"], "words": st["words"], "rank": REPORT_STATES.index(st["state"]),
            "revision": st["revision"],
            "completedOn": _date(st["completedAt"]),
            "last": _date(st["last"]), "lastAt": st["last"].isoformat() if st["last"] else "",
            "note": "" if p["counted"] else "No longer takes this course",
        })
    rows.sort(key=lambda r: r["name"].lower())
    counts = {s: sum(1 for r in rows if r["state"] == s) for s in REPORT_STATES}
    return {"course": summary(course, settings), "people": rows, "counts": counts}


def person_answers(course: Course, progress: list[dict[str, Any]],
                   completions: list[dict[str, Any]]) -> dict[str, Any]:
    """One person's checkpoint answers: every completion, newest first, with
    the answers copied in when it was recorded; then the answers saved so far
    when they have not completed the current revision."""
    done = []
    for c in sorted(completions, key=lambda c: c["completed_at"], reverse=True):
        answers = c.get("answers") or {}
        done.append({"revision": c["revision"], "date": _date(c["completed_at"]),
                     "answers": [{"key": k, "question": v.get("question", ""),
                                  "section": v.get("section", ""), "answer": v.get("answer", "")}
                                 for k, v in answers.items()]})
    current = None
    if not current_completion(course, completions):
        have = {r["item_key"]: r for r in live_progress(course, progress)}
        rows = [{"key": i["key"], "question": i["label"], "section": i["section"],
                 "answer": (have.get(i["key"]) or {}).get("answer") or ""}
                for i in course.items if i["kind"] == "checkpoint"]
        if any(r["answer"] for r in rows):
            current = {"revision": course.revision, "answers": rows}
    return {"completions": done, "current": current}
