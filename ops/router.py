"""FastAPI routes for the operations console (``/ops/api``).

Reuses the assignment dashboard's EspoCRM team-based login/session
(``assignments.auth``) — one staff session covers both tools. The durable store
is read from ``request.app.state.submission_store`` (set by ``create_app``).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from assignments.auth import (
    AuthError,
    authenticate,
    clear_session,
    current_user,
    set_session,
)
from core.config import get_settings

router = APIRouter(prefix="/ops/api", tags=["ops"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


def _require_user(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user


def _store(request: Request):
    store = getattr(request.app.state, "submission_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Durable store is not configured.")
    return store


@router.post("/login")
async def login(body: LoginIn, request: Request) -> dict:
    try:
        user = await authenticate(get_settings(), body.username, body.password)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    set_session(request, user)
    return {"userName": user["userName"], "name": user["name"], "isAdmin": user["isAdmin"]}


@router.post("/logout")
async def logout(request: Request) -> dict:
    clear_session(request)
    return {"status": "ok"}


@router.get("/session")
async def session(request: Request) -> dict:
    user = _require_user(request)
    return {"userName": user["userName"], "name": user["name"], "isAdmin": user["isAdmin"]}


@router.get("/submissions")
async def submissions(
    request: Request,
    status: Optional[str] = Query(default=None),
    form: Optional[str] = Query(default=None),
) -> dict:
    _require_user(request)
    store = _store(request)
    rows = await store.list_submissions(status=status, form=form)
    counts = await store.counts_by_status()
    return {"submissions": rows, "counts": counts}


@router.get("/metrics")
async def metrics(request: Request) -> dict:
    _require_user(request)
    store = _store(request)
    return await store.metrics()


@router.get("/submissions/{submission_id}")
async def submission_detail(submission_id: str, request: Request) -> dict:
    _require_user(request)
    store = _store(request)
    row = await store.get_submission(submission_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Submission not found.")
    return row


@router.post("/submissions/{submission_id}/redrive")
async def redrive(submission_id: str, request: Request) -> dict:
    _require_user(request)
    store = _store(request)
    if not await store.redrive(submission_id):
        raise HTTPException(status_code=404, detail="Submission not found.")
    return {"status": "requeued"}
