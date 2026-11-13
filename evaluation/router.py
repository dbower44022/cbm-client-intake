"""The client's public survey page (phase 1, step 8).

    GET  /evaluation/{token}                    the page, or one polite "no longer valid" page
    GET  /api/evaluation/{token}                the company name, consent, each survey and its answers
    POST /api/evaluation/{token}/consent        consent (ruling BE11), honeypot
    PUT  /api/evaluation/{token}/answers/{key}  save as the client goes (ruling BE13)
    POST /api/evaluation/{token}/submit/{key}   check, lock, write to the CRM; honeypot, idempotent

Every address answers 404 while ``BUSINESS_EVALUATION`` is off
(``core/app.py``). A token that is malformed, unknown, expired or replaced
gets the same answer, and that check never calls the CRM. No CRM id appears in
the page or in any answer here.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from core.branding import render_page
from core.config import get_settings

from . import service
from .surveys import PROFILE_KEY, Survey, SurveyError, load_all

log = logging.getLogger("cbm_intake.evaluation")

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
NO_LONGER_VALID = "This link is no longer valid."
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,64}$")
#: Saves are PUT, which the intake middleware does not cap; they are capped here.
MAX_SAVE_BYTES = 256 * 1024

router = APIRouter(tags=["evaluation-public"])

_surveys: Optional[dict[str, Survey]] = None


def load_surveys() -> Optional[dict[str, Survey]]:
    """Read and check every survey definition. Called at start-up; an invalid
    definition is logged as an ERROR and the pages answer "no longer valid"
    rather than the application failing to start with the feature dark.
    ``tests/test_evaluation_surveys.py`` is what stops one being shipped."""
    global _surveys
    try:
        _surveys = load_all()
    except SurveyError as exc:
        log.error("evaluation survey definitions are invalid: %s", exc)
        _surveys = None
    return _surveys


def surveys() -> Optional[dict[str, Survey]]:
    return _surveys if _surveys is not None else load_surveys()


def _invalid_page() -> HTMLResponse:
    page = (FRONTEND_DIR / "invalid.html").read_text(encoding="utf-8")
    return HTMLResponse(render_page(page, get_settings()), status_code=404)


def _gone() -> HTTPException:
    return HTTPException(status_code=404, detail=NO_LONGER_VALID)


async def _open_link(request: Request, token: str) -> tuple[Any, dict[str, Any], dict[str, Survey]]:
    store = getattr(request.app.state, "evaluation_store", None)
    loaded = surveys()
    if store is None or loaded is None or not _TOKEN.match(token or ""):
        raise _gone()
    link = await store.link_by_token(token)
    if not service.link_is_open(link):
        raise _gone()
    return store, link, loaded


def _client(request: Request):
    factory = getattr(request.app.state, "evaluation_client", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="The service is not available just now.")
    return factory()


def _row_for(rows: list[dict[str, Any]], key: str) -> Optional[dict[str, Any]]:
    return next((r for r in rows if r["survey_key"] == key), None)


def _survey_view(survey: Survey, row: Optional[dict[str, Any]]) -> dict[str, Any]:
    return {
        "key": survey.key,
        "title": survey.title,
        "introduction": survey.introduction,
        "state": service.state_of(row),
        "answers": (row or {}).get("answers") or {},
        "sections": [{
            "title": s.title, "intro": s.intro,
            "questions": [{
                "id": q.id, "label": q.label, "help": q.help, "type": q.type,
                "required": q.required, "options": list(q.options), "max": q.max,
                "low": q.low, "high": q.high,
            } for q in s.questions],
        } for s in survey.sections],
    }


def _survey_for(loaded: dict[str, Survey], row: Optional[dict[str, Any]]) -> Optional[Survey]:
    return loaded.get(row["survey_version"]) if row else None


@router.get("/evaluation/{token}", response_class=HTMLResponse, include_in_schema=False)
async def page(token: str, request: Request) -> HTMLResponse:
    try:
        await _open_link(request, token)
    except HTTPException:
        return _invalid_page()
    html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(render_page(html, get_settings()))


@router.get("/api/evaluation/{token}")
async def state(token: str, request: Request) -> dict[str, Any]:
    store, link, loaded = await _open_link(request, token)
    rows = await store.answers_for(link["id"])
    views = []
    for key in service.survey_keys(link):
        row = _row_for(rows, key)
        survey = _survey_for(loaded, row)
        if survey is not None:
            views.append(_survey_view(survey, row))
    return {
        "company": link.get("company_name") or "",
        "consentGiven": bool(link.get("consent_at")),
        "surveys": views,
    }


@router.post("/api/evaluation/{token}/consent")
async def consent(token: str, request: Request) -> dict[str, Any]:
    store, link, _ = await _open_link(request, token)
    body = await _json(request)
    if str(body.get("company_url") or "").strip():
        log.info("evaluation consent honeypot on link %s", link["id"])
        return {"consentGiven": True}
    if body.get("consent") is not True:
        raise HTTPException(status_code=422, detail="Please tick the box to give your consent.")
    await store.set_consent(link["id"], service.utcnow())
    return {"consentGiven": True}


async def _json(request: Request) -> dict[str, Any]:
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > MAX_SAVE_BYTES:
        raise HTTPException(status_code=413, detail="Your answers are too long to save.")
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="That could not be read.") from None
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="That could not be read.")
    return body


def _needs_consent(link: dict[str, Any]) -> None:
    if not link.get("consent_at"):
        raise HTTPException(status_code=403, detail="Please give your consent before answering.")


@router.put("/api/evaluation/{token}/answers/{key}")
async def save(token: str, key: str, request: Request,
               background: BackgroundTasks) -> dict[str, Any]:
    store, link, loaded = await _open_link(request, token)
    _needs_consent(link)
    if key not in service.survey_keys(link):
        raise _gone()
    body = await _json(request)
    rows = await store.answers_for(link["id"])
    row = _row_for(rows, key)
    survey = _survey_for(loaded, row)
    if survey is None:
        raise _gone()
    if row.get("submitted_at"):
        raise HTTPException(status_code=409,
                            detail="This survey has been submitted and can no longer be changed.")
    answers, _errors = service.clean_answers(survey, body.get("answers"))
    now = service.utcnow()
    saved = await store.save_answers(link["id"], key, answers, now)
    if saved is None:
        raise HTTPException(status_code=409,
                            detail="This survey has been submitted and can no longer be changed.")
    if answers and saved.get("crm_record_id") and await store.mark_started(saved["id"], now):
        background.add_task(service.mark_in_progress, _client(request), saved["crm_record_id"])
    return {"state": service.state_of(saved), "savedAt": now.isoformat()}


@router.post("/api/evaluation/{token}/submit/{key}")
async def submit(token: str, key: str, request: Request) -> JSONResponse:
    store, link, loaded = await _open_link(request, token)
    body = await _json(request)
    if str(body.get("company_url") or "").strip():
        log.info("evaluation submit honeypot on link %s", link["id"])
        return JSONResponse({"state": service.SUBMITTED, "delivered": True})
    _needs_consent(link)
    if key not in service.survey_keys(link):
        raise _gone()
    rows = await store.answers_for(link["id"])
    row = _row_for(rows, key)
    survey = _survey_for(loaded, row)
    if survey is None:
        raise _gone()
    if row.get("submitted_at"):
        # A repeated press, or a second tab: the first submit stands.
        return JSONResponse({"state": service.SUBMITTED, "delivered": bool(row.get("delivered_at"))})
    token_value = str(body.get("submission_token") or "")[:64]
    if not token_value:
        raise HTTPException(status_code=400, detail="That could not be read.")
    answers, errors = service.clean_answers(survey, body.get("answers"))
    errors.update({k: v for k, v in service.missing_required(survey, answers).items()
                   if k not in errors})
    now = service.utcnow()
    if errors:
        await store.save_answers(link["id"], key, answers, now)
        return JSONResponse(status_code=422, content={
            "detail": "Some questions still need an answer. They are marked below.",
            "errors": errors,
        })
    locked = await store.submit(link["id"], key, answers, token_value, now)
    if locked is None:
        raise _gone()
    if locked.get("delivered_at"):
        return JSONResponse({"state": service.SUBMITTED, "delivered": True})
    delivered = await service.deliver_row(store, _client(request), link, locked, loaded)
    return JSONResponse({"state": service.SUBMITTED, "delivered": delivered})


__all__ = ["router", "load_surveys", "surveys", "FRONTEND_DIR", "PROFILE_KEY"]
