"""The Business Evaluation analysis (plan § 3 step 4; rulings BE6, BE9, BE15,
BE16, BE17): the worker pass that turns a Submitted record into a draft
report through the Claude API.

Rules kept here:

* **One Claude API call per area**, structured output checked against
  ``report.Report`` (``messages.parse``, the ``comms/summarize.py`` pattern).
* **The CRM status is the queue.** The pass picks up Submitted records;
  success sets Draft Ready, failure sets Analysis Failed with
  ``analysisError``, and Retry on the Evaluations tab sets Submitted again.
  No table in the application database.
* **No contact details reach the Claude API** (``scrub``): email addresses,
  phone numbers and street addresses in the owner's own text are replaced by
  ``[removed]``. The company name and the business profile are sent.
* **The prompt and the rubric are versioned files** (BE9),
  ``prompts/<key>.v<n>.yaml`` and ``rubrics/<key>.v<n>.yaml``,
  beside the survey definitions;
  the record stores ``promptVersion`` and ``rubricVersion``.
* **The draft report never reaches the client** (BE17). It is written to the
  record and shown on the Evaluations tab; ``reviewedReport`` starts as a
  copy (plan § 5).
* **The mentor is told by email** (Doug's choice A, 11-14-26): from the shared
  mailbox to the engagement mentor's ``cbmEmail``, best-effort, never failing
  the analysis.
* **Every call's tokens and cost are logged.**

Off unless ``BUSINESS_EVALUATION`` is on, ``EVALUATION_ANALYSIS_SECONDS`` is
above 0, the Anthropic integration is in use and ``ANTHROPIC_API_KEY`` is set.
"""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from core.branding import MODE_TEXT, abbr, render as render_branding
from core.espo import EspoError

from . import report as report_mod
from . import service
from .surveys import AREAS, PROFILE_KEY, Survey, latest

log = logging.getLogger("cbm_intake.evaluation.analysis")

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
RUBRIC_DIR = Path(__file__).resolve().parent / "rubrics"

STATUS_SUBMITTED = service.STATUS_SUBMITTED
STATUS_DRAFT_READY = "Draft Ready"
STATUS_FAILED = "Analysis Failed"

#: Records picked up per pass.
BATCH = 10
#: How long an area submitted before the business profile waits for it.
PROFILE_WAIT = timedelta(hours=24)
MAX_TOKENS = 16000
FALLBACK_BETA = "server-side-fallback-2026-07-01"
ERROR_MAX = 2000

REMOVED = "[removed]"


class AnalysisError(Exception):
    """An analysis that cannot be completed, with a message a mentor can read."""


# --- the prompt and rubric files (BE9) ------------------------------------------

@dataclass(frozen=True)
class Dimension:
    id: str
    name: str
    informed_by: tuple[str, ...]
    levels: dict[int, str]
    note: str = ""


@dataclass(frozen=True)
class Rubric:
    key: str
    version: int
    area: str
    dimensions: tuple[Dimension, ...]

    @property
    def ref(self) -> str:
        return f"{self.key}.v{self.version}"


@dataclass(frozen=True)
class Prompt:
    key: str
    version: int
    area: str
    rubric: str
    system: str

    @property
    def ref(self) -> str:
        return f"{self.key}.v{self.version}"


_NAME = re.compile(r"^([a-z0-9-]+)\.v(\d+)\.yaml$")


def _files(directory: Path) -> list[tuple[str, int, Path]]:
    out = []
    for path in sorted(directory.glob("*.yaml")):
        m = _NAME.match(path.name)
        if not m:
            raise AnalysisError(f"{path.name}: the file name must be <key>.v<n>.yaml")
        out.append((m.group(1), int(m.group(2)), path))
    return out


def _read(path: Path, key: str, version: int) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AnalysisError(f"{path.name}: not a mapping")
    if raw.get("key") != key or raw.get("version") != version:
        raise AnalysisError(f"{path.name}: key and version must match the file name")
    if raw.get("area") not in AREAS:
        raise AnalysisError(f"{path.name}: area {raw.get('area')!r} is not an evaluation area")
    return raw


def _rubric(path: Path, key: str, version: int) -> Rubric:
    raw = _read(path, key, version)
    dims = []
    for d in raw.get("dimensions") or []:
        levels = {int(k): str(v).strip() for k, v in (d.get("levels") or {}).items()}
        if sorted(levels) != [1, 2, 3, 4, 5] or not all(levels.values()):
            raise AnalysisError(f"{path.name}: {d.get('id')} must describe levels 1 to 5")
        if not d.get("id") or not d.get("name"):
            raise AnalysisError(f"{path.name}: every dimension needs an id and a name")
        dims.append(Dimension(id=d["id"], name=d["name"],
                              informed_by=tuple(d.get("informed_by") or ()),
                              levels=levels, note=str(d.get("note") or "").strip()))
    if not dims or len({d.id for d in dims}) != len(dims):
        raise AnalysisError(f"{path.name}: needs dimensions with distinct ids")
    return Rubric(key=key, version=version, area=raw["area"], dimensions=tuple(dims))


def _prompt(path: Path, key: str, version: int) -> Prompt:
    raw = _read(path, key, version)
    system = str(raw.get("system") or "").strip()
    if not system or not raw.get("rubric"):
        raise AnalysisError(f"{path.name}: needs system text and a rubric")
    return Prompt(key=key, version=version, area=raw["area"], rubric=raw["rubric"],
                  system=system)


def load_all() -> tuple[dict[str, Prompt], dict[str, Rubric]]:
    """Every prompt and rubric, keyed by version name (``finance.v1``).
    Raises ``AnalysisError`` on an invalid file or a prompt naming a rubric
    that does not exist."""
    prompts = {f"{k}.v{v}": _prompt(p, k, v) for k, v, p in _files(PROMPT_DIR)}
    rubrics = {f"{k}.v{v}": _rubric(p, k, v) for k, v, p in _files(RUBRIC_DIR)}
    for p in prompts.values():
        r = rubrics.get(p.rubric)
        if r is None:
            raise AnalysisError(f"{p.ref}: names rubric {p.rubric}, which does not exist")
        if r.area != p.area:
            raise AnalysisError(f"{p.ref}: its rubric {r.ref} is for {r.area}")
    return prompts, rubrics


def prompt_for(prompts: dict[str, Prompt], area: str) -> Optional[Prompt]:
    """The latest prompt for an evaluation area, or None."""
    found = [p for p in prompts.values() if p.area == area]
    return max(found, key=lambda p: p.version, default=None)


def rubric_text(rubric: Rubric) -> str:
    """The rubric as the system prompt's last section."""
    lines = ["THE RUBRIC",
             "Score these dimensions, in this order. Use each dimension's id in "
             "scores.dimension_id."]
    for n, d in enumerate(rubric.dimensions, start=1):
        lines.append("")
        lines.append(f"{n}. {d.name} (id: {d.id})")
        if d.informed_by:
            lines.append(f"   Rests on the answers: {', '.join(d.informed_by)}")
        if d.note:
            lines.append(f"   Note: {d.note}")
        for level in range(1, 6):
            lines.append(f"   {level}: {d.levels[level]}")
    return "\n".join(lines)


def system_text(prompt: Prompt, rubric: Rubric, settings: Any) -> str:
    return render_branding(prompt.system, settings, MODE_TEXT) + "\n\n" + rubric_text(rubric)


# --- what is sent: the answers, scrubbed --------------------------------------

_EMAIL = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Ten or more digits with the usual separators, an optional +country code.
_PHONE = re.compile(r"(?<![\w$])\+?\d[\d\s().-]{8,}\d(?!\w)")
_STREET_WORDS = (
    r"street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|lane|ln|court|ct|way|"
    r"place|pl|parkway|pkwy|terrace|ter|circle|cir|highway|hwy|suite|ste")
_STREET = re.compile(
    rf"\b\d{{1,6}}(?:\s+[A-Z0-9][\w'.-]*){{1,4}}\s+(?:{_STREET_WORDS})\b\.?",
    re.IGNORECASE)
_PO_BOX = re.compile(r"\bP\.?\s*O\.?\s*Box\s+\d+\b", re.IGNORECASE)


def _phone_like(match: re.Match) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return REMOVED if 10 <= len(digits) <= 15 else match.group(0)


def scrub(text: str) -> str:
    """The owner's text with email addresses, phone numbers and street
    addresses replaced by ``[removed]``."""
    if not text:
        return text
    out = _EMAIL.sub(REMOVED, text)
    out = _PHONE.sub(_phone_like, out)
    out = _PO_BOX.sub(REMOVED, out)
    return _STREET.sub(REMOVED, out)


def _shown(value: Any) -> Any:
    if value is None or value == "" or value == []:
        return "Not answered"
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, list):
        return [scrub(v) if isinstance(v, str) else v for v in value]
    return value


def questions_and_answers(survey: Survey, answers: dict[str, Any]) -> list[dict[str, Any]]:
    """Every question of the survey, in order, with the owner's answer
    (scrubbed) or "Not answered"."""
    out = []
    for section in survey.sections:
        for q in section.questions:
            item: dict[str, Any] = {"id": q.id, "section": section.title,
                                    "question": q.label, "answer": _shown(answers.get(q.id))}
            if q.type == "scale" and q.low and q.high:
                item["scale"] = f"1 = {q.low}, 5 = {q.high}"
            out.append(item)
    return out


def _parse_answers(raw: str, surveys: dict[str, Survey], fallback_key: str
                   ) -> tuple[Optional[Survey], dict[str, Any]]:
    """The survey and answers from a stored ``answers_json`` value."""
    try:
        data = json.loads(raw or "")
    except ValueError:
        return None, {}
    if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        return None, {}
    survey = surveys.get(data.get("survey") or "") or latest(surveys, fallback_key)
    return survey, data["answers"]


def user_message(company: str, profile: Optional[tuple[Survey, dict]], area: tuple[Survey, dict]
                 ) -> str:
    """The message the Claude API receives: the company name, the business
    profile and the area's answers, as JSON. No contact details."""
    payload: dict[str, Any] = {"company": company or "(not given)"}
    if profile is not None:
        payload["business_profile"] = questions_and_answers(*profile)
    else:
        payload["business_profile"] = ("The owner has not answered the business "
                                       "profile. Say so in points_to_check.")
    survey, answers = area
    payload[f"{survey.title.lower()}_survey"] = questions_and_answers(survey, answers)
    return json.dumps(payload, ensure_ascii=False, indent=1)


# --- the call ------------------------------------------------------------------

def tidy(rep: report_mod.Report, rubric: Rubric) -> report_mod.Report:
    """The scores in the rubric's order, one per dimension: a score outside 1
    to 5 becomes "Not scored", a dimension the reply missed is added as not
    scored, and one the rubric does not have is dropped."""
    by_id = {s.dimension_id: s for s in rep.scores}
    scores = []
    for d in rubric.dimensions:
        s = by_id.get(d.id)
        if s is None:
            scores.append(report_mod.DimensionScore(
                dimension_id=d.id, score=None,
                reason="The analysis gave no score for this; a reviewer should add one."))
        elif s.score is not None and s.score not in (1, 2, 3, 4, 5):
            scores.append(s.model_copy(update={"score": None}))
        else:
            scores.append(s)
    return rep.model_copy(update={"scores": scores})


@dataclass
class CallResult:
    report: report_mod.Report
    model: str
    input_tokens: int
    output_tokens: int
    cost: float


async def call_claude(client: Any, model: str, system: str, message: str) -> CallResult:
    """One analysis call. Raises ``AnalysisError`` on a refusal, a cut-off
    reply or a reply that does not fit the schema; the SDK's own errors pass
    through."""
    resp = await client.beta.messages.parse(
        model=model,
        max_tokens=MAX_TOKENS,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=system,
        messages=[{"role": "user", "content": message}],
        output_format=report_mod.Report,
    )
    used = getattr(resp, "model", None) or model
    usage = getattr(resp, "usage", None)
    from enrichment.research import usage_cost

    cost, _ = usage_cost(usage, used)
    tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
    tokens_out = int(getattr(usage, "output_tokens", 0) or 0)
    log.info("evaluation analysis call: model=%s input_tokens=%d output_tokens=%d cost=$%.4f",
             used, tokens_in, tokens_out, cost)
    if resp.stop_reason == "refusal":
        raise AnalysisError("The AI service declined to write this report.")
    if resp.stop_reason == "max_tokens":
        raise AnalysisError("The AI service's reply was cut off before the report was complete.")
    parsed = getattr(resp, "parsed_output", None)
    if parsed is None:
        raise AnalysisError("The AI service's reply was not a report in the expected form.")
    return CallResult(report=parsed, model=used, input_tokens=tokens_in,
                      output_tokens=tokens_out, cost=cost)


# --- the pass ------------------------------------------------------------------

def enabled(settings: Any) -> bool:
    return bool(settings.business_evaluation and settings.evaluation_analysis_seconds > 0
                and settings.anthropic_in_use and (settings.anthropic_api_key or "").strip()
                and not settings.espo_dry_run)


def _crm_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _error_text(exc: BaseException) -> str:
    if isinstance(exc, AnalysisError):
        text = str(exc)
    else:
        text = f"The AI service could not be reached or refused the request ({type(exc).__name__}: {exc})."
    return text[:ERROR_MAX]


async def analyze_record(rec: dict[str, Any], *, crm: Any, claude: Any, settings: Any,
                         surveys: dict[str, Survey], prompts: dict[str, Prompt],
                         rubrics: dict[str, Rubric], now: datetime) -> Optional[str]:
    """Analyze one Submitted record. Returns the new status, or None when the
    record waits (its business profile is not in yet). Raises ``EspoError``
    when the CRM cannot be read or written; every other failure is written
    to the record as Analysis Failed."""
    area = rec.get("evaluationArea") or ""
    prompt = prompt_for(prompts, area)
    profile_raw, company = "", ""
    if rec.get("clientProfileId"):
        prof = await crm.get(service.CLIENT_PROFILE, rec["clientProfileId"],
                             select="name,linkedCompanyName,evaluationProfile")
        profile_raw = prof.get("evaluationProfile") or ""
        company = prof.get("linkedCompanyName") or prof.get("name") or ""
    profile_survey, profile_answers = _parse_answers(profile_raw, surveys, PROFILE_KEY)
    if profile_survey is None:
        submitted = _crm_time(rec.get("submittedAt"))
        if submitted is not None and now - submitted < PROFILE_WAIT:
            return None
    try:
        if prompt is None:
            raise AnalysisError(f"There is no analysis prompt for {area or 'this area'} yet.")
        rubric = rubrics[prompt.rubric]
        area_key = prompt.key
        area_survey, area_answers = _parse_answers(rec.get("answers") or "", surveys, area_key)
        if area_survey is None:
            raise AnalysisError("The client's answers on this record could not be read.")
        message = user_message(
            company,
            (profile_survey, profile_answers) if profile_survey is not None else None,
            (area_survey, area_answers))
        result = await call_claude(claude, settings.evaluation_model,
                                   system_text(prompt, rubric, settings), message)
        rep = tidy(result.report, rubric)
        draft = report_mod.render(rep, area=area, company=company,
                                  dimension_names={d.id: d.name for d in rubric.dimensions})
    except EspoError:
        raise
    except Exception as exc:  # noqa: BLE001 — written to the record for Retry
        log.warning("evaluation %s: analysis failed: %s", rec.get("id"), exc)
        await crm.update(service.ENTITY, rec["id"], {
            "status": STATUS_FAILED, "analysisError": _error_text(exc),
            "promptVersion": prompt.ref if prompt else None,
            "rubricVersion": prompt.rubric if prompt else None,
        })
        return STATUS_FAILED
    await crm.update(service.ENTITY, rec["id"], {
        "draftReport": draft,
        "reviewedReport": draft,
        "scores": json.dumps({s.dimension_id: {"score": s.score, "reason": s.reason}
                              for s in rep.scores}, ensure_ascii=False),
        "analyzedAt": service.crm_stamp(now),
        "promptVersion": prompt.ref,
        "rubricVersion": rubric.ref,
        "analysisError": "",
        "status": STATUS_DRAFT_READY,
    })
    log.info("evaluation %s: draft ready (%s, %s, %s; $%.4f)", rec["id"], area,
             prompt.ref, rubric.ref, result.cost)
    return STATUS_DRAFT_READY


async def submitted_records(crm: Any) -> list[dict[str, Any]]:
    page = await crm.list(service.ENTITY, where=[
        {"type": "equals", "attribute": "status", "value": STATUS_SUBMITTED}],
        select=("id,name,evaluationArea,evaluationRound,engagementId,clientProfileId,"
                "answers,submittedAt"),
        max_size=BATCH, order_by="submittedAt", order="asc")
    return page.get("list", []) or []


async def run_analysis_cycle(settings: Any, crm: Any, claude: Any, *,
                             surveys: dict[str, Survey],
                             notify: Optional[Callable[..., Any]] = None,
                             now: Optional[datetime] = None) -> dict[str, int]:
    """One pass: every Submitted record (up to ``BATCH``) analyzed. Returns
    counts by outcome. Never raises."""
    counts = {"ready": 0, "failed": 0, "waiting": 0, "crmErrors": 0}
    now = now or service.utcnow()
    try:
        prompts, rubrics = load_all()
        records = await submitted_records(crm)
    except AnalysisError as exc:
        log.error("evaluation analysis: the prompt or rubric files are invalid: %s", exc)
        return counts
    except EspoError as exc:
        log.warning("evaluation analysis: the submitted records could not be read: %s", exc)
        counts["crmErrors"] += 1
        return counts
    for rec in records:
        try:
            outcome = await analyze_record(rec, crm=crm, claude=claude, settings=settings,
                                           surveys=surveys, prompts=prompts,
                                           rubrics=rubrics, now=now)
        except EspoError as exc:
            log.warning("evaluation %s: the CRM refused the analysis read or write: %s",
                        rec.get("id"), exc)
            counts["crmErrors"] += 1
            continue
        if outcome is None:
            counts["waiting"] += 1
        elif outcome == STATUS_DRAFT_READY:
            counts["ready"] += 1
            if notify is not None:
                try:
                    await notify(rec)
                except Exception as exc:  # noqa: BLE001 — never fails the analysis
                    log.warning("evaluation %s: the mentor was not told: %s", rec.get("id"), exc)
        else:
            counts["failed"] += 1
    if any(counts.values()):
        log.info("evaluation analysis pass: %s", counts)
    return counts


# --- telling the mentor (Doug's choice A, 11-14-26) ------------------------------

def notice_email(*, area: str, company: str, url: str) -> tuple[str, str]:
    """The subject and HTML body of the draft-ready email to the mentor."""
    who = f"{area} — {company}" if company else area
    subject = f"{abbr()}: draft evaluation ready to review: {who}"
    link = (f'<p><a href="{html.escape(url, quote=True)}">Open the Evaluations tab</a></p>'
            if url else "<p>Open the engagement in Client Management, Evaluations tab.</p>")
    body = (
        f"<p>The draft {html.escape(area)} evaluation report for "
        f"{html.escape(company or 'your client')} is ready for you to review.</p>"
        "<p>Your client has not seen it. Read it with the client's answers, correct "
        "it, and then go through it with the client at a review session.</p>"
        f"{link}"
    )
    return subject, body


async def mentor_address(crm: Any, engagement_id: str) -> str:
    """The engagement mentor's cbmEmail, or "" when there is none."""
    eng = await crm.get(service.ENGAGEMENT, engagement_id, select="mentorProfileId")
    if not eng.get("mentorProfileId"):
        return ""
    prof = await crm.get("CMentorProfile", eng["mentorProfileId"], select="cbmEmail")
    return (prof.get("cbmEmail") or "").strip().lower()


def make_notifier(settings: Any, crm: Any) -> Callable[[dict[str, Any]], Any]:
    """The draft-ready email, sent from the shared mailbox. Logs and skips
    when there is no shared mailbox or no mentor address."""

    async def notify(rec: dict[str, Any]) -> None:
        if not (settings.ops_mailbox or "").strip():
            log.info("evaluation %s: draft ready; no shared mailbox, so no email", rec.get("id"))
            return
        to = await mentor_address(crm, rec.get("engagementId") or "")
        if not to:
            log.info("evaluation %s: draft ready; the engagement has no mentor address",
                     rec.get("id"))
            return
        name = rec.get("name") or ""
        company = name.split(" — ", 1)[1] if " — " in name else ""
        base = (settings.app_base_url or "").strip().rstrip("/")
        url = (f"{base}/mentorsessions/record/{rec.get('engagementId')}?tab=evaluations"
               if base else "")
        subject, body = notice_email(area=rec.get("evaluationArea") or "", company=company,
                                     url=url)
        from comms import service as comms_service

        gmail = await comms_service.gmail_for_shared_mailbox(settings, settings.ops_mailbox)
        try:
            await comms_service.send_quick_message(
                gmail=gmail, to=[to], subject=subject, body_html=body,
                sender_name=settings.sender_display_name)
        finally:
            await gmail.aclose()
        log.info("evaluation %s: draft-ready email sent to the mentor", rec.get("id"))

    return notify
