"""Training course routes (prds/training-app-plan.md § 5.2, phase 1).

``/api/courses``: the member's list, one course's page material and saved
progress, saving a tick or an answer, and completing the course. Behind
``TRAINING_COURSES``, read per request: off, every route answers 404
(decision 11). Signed in, and able to open one of the course's applications
(TR2, TR3); a course the member may not take answers 404 in the same words
as an unknown id, like every other gated record in this application.

Ticks, answers and completions are the application's own data (decision
12): no CRM call and no action log entry.

**A save is refused when the browser's sign-in is no longer the person the
page was opened for** (v0.362.2, found at stop 1, 11-21-26). One browser
holds one sign-in per site, and where the training system is this same
application (the Association), signing in to an exercise as a training
login used to send the course page's next save in as that login. Every
save and Complete course carry ``asUser``, the person the page was opened
for; a different session answers 409 and nothing is written.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from assignments.auth import current_user
from core.config import Settings, get_settings

from . import service
from .catalog import Course
from .store import course_store

log = logging.getLogger("cbm_intake.courses")

router = APIRouter(prefix="/api/courses", tags=["courses"])

NOT_FOUND = "That course was not found."
MAX_ANSWER = 2000


def _member(request: Request) -> tuple[dict[str, Any], Settings]:
    settings = get_settings()
    if not settings.training_courses:
        raise HTTPException(status_code=404, detail="Not found.")
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user, settings


def _store(settings: Settings):
    store = course_store(settings)
    if store is None:
        raise HTTPException(status_code=503, detail=(
            "Training courses need the application's database, which this server does not have."))
    return store


def _course(course_id: str, user: dict[str, Any], settings: Settings) -> Course:
    course = service.courses(settings).get(course_id)
    if course is None or not service.may_take(course, service.routes_for(user, settings)):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return course


def _uid(user: dict[str, Any]) -> str:
    return user.get("userId") or ""


def _name(user: dict[str, Any]) -> str:
    return user.get("name") or user.get("userName") or ""


def _same_person(user: dict[str, Any], as_user: Optional[str], as_name: Optional[str]) -> None:
    """409 unless the session is still the person the page was opened for."""
    if not as_user:
        raise HTTPException(status_code=409, detail=(
            "This course page is out of date. Reload it, then tick the step again."))
    if as_user != _uid(user):
        raise HTTPException(status_code=409, detail=(
            f"This course is {as_name or 'another person'}'s, but this browser is now signed in "
            f"as {_name(user) or 'someone else'}. Nothing was saved. Keep the course in a normal "
            "window and sign in to the exercises in a private window, then reload this page."))


def _completion_view(row: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not row:
        return None
    return {"revision": row["revision"], "completedAt": row["completed_at"].isoformat(),
            "date": service._date(row["completed_at"])}


@router.get("/mine")
async def mine(request: Request, app: str = "") -> dict:
    """The member's courses (decision 8): those of ``app`` first, then the
    others they can take, each with its status."""
    user, settings = _member(request)
    store = _store(settings)
    routes = service.routes_for(user, settings)
    progress = await store.progress_counts(_uid(user))
    completions = await store.completions(_uid(user))
    app = (app or "").strip().strip("/")
    first, rest = [], []
    for course in service.courses(settings).values():
        if not service.may_take(course, routes):
            continue
        row = {**service.summary(course, settings),
               "status": service.status(course, progress.get(course.id, []), completions),
               "forApp": bool(app) and app in course.applications}
        (first if row["forApp"] else rest).append(row)
    return {"user": {"name": user.get("name") or user.get("userName") or ""},
            "app": app, "courses": first + rest}


@router.get("/{course_id}")
async def course_page(course_id: str, request: Request) -> dict:
    """The course page's material and this member's saved progress. Ticks
    made against an earlier significant revision are cleared here, and the
    page is told so (decision 6)."""
    user, settings = _member(request)
    store = _store(settings)
    course = _course(course_id, user, settings)
    rows = await store.progress(_uid(user), course.id)
    stale = service.stale_keys(course, rows)
    notice = ""
    if stale:
        await store.clear_items(_uid(user), course.id, stale)
        notice = (f"This course changed significantly (it is now revision {course.revision}), "
                  "so your earlier ticks and answers were cleared. Please start again.")
    live = service.live_progress(course, rows)
    completion = service.current_completion(course, await store.completions(_uid(user)))
    return {
        **service.page(course, settings),
        "user": {"id": _uid(user), "name": _name(user)},
        "progress": {r["item_key"]: {"answer": r.get("answer"), "at": r["done_at"].isoformat()}
                     for r in live},
        "completion": _completion_view(completion),
        "notice": notice,
    }


class ItemIn(BaseModel):
    done: bool = True
    answer: Optional[str] = Field(default=None, max_length=MAX_ANSWER)
    asUser: Optional[str] = Field(default=None, max_length=64)
    asName: Optional[str] = Field(default=None, max_length=255)


class CompleteIn(BaseModel):
    asUser: Optional[str] = Field(default=None, max_length=64)
    asName: Optional[str] = Field(default=None, max_length=255)


@router.put("/{course_id}/items/{item_key}")
async def save_item(course_id: str, item_key: str, body: ItemIn, request: Request) -> dict:
    """Save one tick (``done``) or one checkpoint answer (``answer``; blank
    clears it) as the trainee goes (decision 6)."""
    user, settings = _member(request)
    _same_person(user, body.asUser, body.asName)
    store = _store(settings)
    course = _course(course_id, user, settings)
    item = next((i for i in course.items if i["key"] == item_key), None)
    if item is None:
        raise HTTPException(status_code=404, detail="That step is not in this course.")
    if item["kind"] == "checkpoint":
        answer = (body.answer or "").strip()
        if not answer:
            await store.clear_item(_uid(user), course.id, item_key)
            return {"key": item_key, "saved": False}
        row = await store.save_item(_uid(user), course.id, course.revision, item_key, answer)
        return {"key": item_key, "saved": True, "at": row["done_at"].isoformat()}
    if not body.done:
        await store.clear_item(_uid(user), course.id, item_key)
        return {"key": item_key, "saved": False}
    row = await store.save_item(_uid(user), course.id, course.revision, item_key, None)
    return {"key": item_key, "saved": True, "at": row["done_at"].isoformat()}


@router.post("/{course_id}/complete")
async def complete(course_id: str, request: Request, body: Optional[CompleteIn] = None) -> dict:
    """Complete the course (TR1). Pressed early, nothing is written and the
    answer names the steps not ticked and the checkpoints not answered
    (decision 7)."""
    user, settings = _member(request)
    body = body or CompleteIn()
    _same_person(user, body.asUser, body.asName)
    store = _store(settings)
    course = _course(course_id, user, settings)
    rows = await store.progress(_uid(user), course.id)
    gaps = service.missing(course, rows)
    if gaps["steps"] or gaps["checkpoints"]:
        return {"completed": False, "missing": gaps}
    row, created = await store.complete(
        _uid(user), _name(user), course.id, course.revision,
        service.answers(course, rows))
    if created:
        log.info("courses: %s completed %s at %s", _uid(user), course.id, course.revision)
    return {"completed": True, "completion": _completion_view(row)}
