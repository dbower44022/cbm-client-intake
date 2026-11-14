"""The public survey page and its API (ruling BE23).

    GET  /survey/{token}                    the page, or one polite "no longer valid" page
    GET  /api/survey/{token}                the display name, consent, each survey and its answers
    POST /api/survey/{token}/consent        consent (ruling BE11), honeypot
    PUT  /api/survey/{token}/answers/{key}  save as the person goes (ruling BE13)
    POST /api/survey/{token}/submit/{key}   check, lock, hand to the purpose; honeypot, idempotent

The page's own CSS and JS are at ``/survey-assets/``. While no survey
purpose's switch is on, every one of these addresses answers 404
(``core/app.py``). A link whose purpose is switched off answers exactly as an
unknown one. A token that is malformed, unknown, expired or replaced gets the
same answer, and that check never calls the CRM. No CRM id appears in the
page or in any answer here.
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

from . import answers as ans
from . import registry, service
from .definitions import Survey
from .registry import SurveyPurpose

log = logging.getLogger("cbm_intake.surveys")

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
NO_LONGER_VALID = "This link is no longer valid."
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,64}$")
#: Saves are PUT, which the intake middleware does not cap; they are capped here.
MAX_SAVE_BYTES = 256 * 1024
#: The page's placeholders for the purpose's words (``registry.PageText``).
_SLOTS = ("title", "consent_intro", "consent_label", "list_intro", "all_done")

router = APIRouter(tags=["survey-public"])


def _invalid_page() -> HTMLResponse:
    page = (FRONTEND_DIR / "invalid.html").read_text(encoding="utf-8")
    return HTMLResponse(render_page(page, get_settings()), status_code=404)


def _gone() -> HTTPException:
    return HTTPException(status_code=404, detail=NO_LONGER_VALID)


async def _open_link(request: Request, token: str
                     ) -> tuple[Any, SurveyPurpose, dict[str, Any], dict[str, Survey]]:
    store = getattr(request.app.state, "survey_store", None)
    if store is None or not _TOKEN.match(token or ""):
        raise _gone()
    link = await store.link_by_token(token)
    if not service.link_is_open(link):
        raise _gone()
    purpose = registry.get(link.get("purpose") or "")
    if purpose is None or not registry.is_on(purpose, get_settings()):
        raise _gone()
    loaded = registry.definitions(purpose.key)
    if loaded is None:
        raise _gone()
    return store, purpose, link, loaded


def _client(request: Request, purpose: SurveyPurpose):
    try:
        client = purpose.client(request.app)
    except Exception as exc:  # noqa: BLE001 — named to the person as unavailable
        log.warning("survey %s: no client: %s", purpose.key, exc)
        client = None
    if client is None:
        raise HTTPException(status_code=503, detail="The service is not available just now.")
    return client


def _row_for(rows: list[dict[str, Any]], key: str) -> Optional[dict[str, Any]]:
    return next((r for r in rows if r["survey_key"] == key), None)


def _survey_view(survey: Survey, row: Optional[dict[str, Any]]) -> dict[str, Any]:
    return {
        "key": survey.key,
        "title": survey.title,
        "introduction": survey.introduction,
        "state": ans.state_of(row),
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


def page_html(purpose: SurveyPurpose) -> str:
    """The page with the purpose's words in place, before the branding tokens."""
    page = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    for slot in _SLOTS:
        page = page.replace(f"[[{slot}]]", getattr(purpose.page, slot))
    return page


@router.get("/survey/{token}", response_class=HTMLResponse, include_in_schema=False)
async def page(token: str, request: Request) -> HTMLResponse:
    try:
        _store, purpose, _link, _loaded = await _open_link(request, token)
    except HTTPException:
        return _invalid_page()
    return HTMLResponse(render_page(page_html(purpose), get_settings()))


@router.get("/api/survey/{token}")
async def state(token: str, request: Request) -> dict[str, Any]:
    store, purpose, link, loaded = await _open_link(request, token)
    rows = await store.answers_for(link["id"])
    views = []
    for key in purpose.surveys_for(link):
        row = _row_for(rows, key)
        survey = _survey_for(loaded, row)
        if survey is not None:
            views.append(_survey_view(survey, row))
    return {
        "displayName": link.get("display_name") or "",
        "consentGiven": bool(link.get("consent_at")),
        "surveys": views,
    }


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


@router.post("/api/survey/{token}/consent")
async def consent(token: str, request: Request) -> dict[str, Any]:
    store, purpose, link, _ = await _open_link(request, token)
    body = await _json(request)
    if str(body.get("company_url") or "").strip():
        log.info("survey %s consent honeypot on link %s", purpose.key, link["id"])
        return {"consentGiven": True}
    if body.get("consent") is not True:
        raise HTTPException(status_code=422, detail="Please tick the box to give your consent.")
    await store.set_consent(link["id"], service.utcnow())
    return {"consentGiven": True}


def _needs_consent(link: dict[str, Any]) -> None:
    if not link.get("consent_at"):
        raise HTTPException(status_code=403, detail="Please give your consent before answering.")


_LOCKED = "This survey has been submitted and can no longer be changed."


@router.put("/api/survey/{token}/answers/{key}")
async def save(token: str, key: str, request: Request,
               background: BackgroundTasks) -> dict[str, Any]:
    store, purpose, link, loaded = await _open_link(request, token)
    _needs_consent(link)
    if key not in purpose.surveys_for(link):
        raise _gone()
    body = await _json(request)
    rows = await store.answers_for(link["id"])
    row = _row_for(rows, key)
    survey = _survey_for(loaded, row)
    if survey is None:
        raise _gone()
    if row.get("submitted_at"):
        raise HTTPException(status_code=409, detail=_LOCKED)
    answers, _errors = ans.clean_answers(survey, body.get("answers"))
    now = service.utcnow()
    saved = await store.save_answers(link["id"], key, answers, now)
    if saved is None:
        raise HTTPException(status_code=409, detail=_LOCKED)
    if answers and purpose.first_save is not None and await store.mark_started(saved["id"], now):
        background.add_task(service.first_save, purpose, _client(request, purpose),
                            link, saved, survey)
    return {"state": ans.state_of(saved), "savedAt": now.isoformat()}


@router.post("/api/survey/{token}/submit/{key}")
async def submit(token: str, key: str, request: Request) -> JSONResponse:
    store, purpose, link, loaded = await _open_link(request, token)
    body = await _json(request)
    if str(body.get("company_url") or "").strip():
        log.info("survey %s submit honeypot on link %s", purpose.key, link["id"])
        return JSONResponse({"state": ans.SUBMITTED, "delivered": True})
    _needs_consent(link)
    if key not in purpose.surveys_for(link):
        raise _gone()
    rows = await store.answers_for(link["id"])
    row = _row_for(rows, key)
    survey = _survey_for(loaded, row)
    if survey is None:
        raise _gone()
    if row.get("submitted_at"):
        # A repeated press, or a second tab: the first submit stands.
        return JSONResponse({"state": ans.SUBMITTED, "delivered": bool(row.get("delivered_at"))})
    token_value = str(body.get("submission_token") or "")[:64]
    if not token_value:
        raise HTTPException(status_code=400, detail="That could not be read.")
    answers, errors = ans.clean_answers(survey, body.get("answers"))
    errors.update({k: v for k, v in ans.missing_required(survey, answers).items()
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
        return JSONResponse({"state": ans.SUBMITTED, "delivered": True})
    delivered = await service.deliver_row(store, purpose, _client(request, purpose), link,
                                          locked, loaded)
    return JSONResponse({"state": ans.SUBMITTED, "delivered": delivered})


__all__ = ["router", "FRONTEND_DIR", "page_html"]
