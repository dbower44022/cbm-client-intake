"""The mentor match (plan § 3b use 2, ruling BE28): the AI analysis a Client
Administration staff member runs on an engagement waiting for a mentor.

Rules kept here (Doug's choices at stopping point (a), 11-19-26):

* **Advice only.** The result names the client's needs, the kind of mentor
  that would suit and up to three mentors with a reason each. Nothing here
  assigns; the staff member still uses Assign.
* **What is sent**: the company name, the intake's focus areas and needs,
  the business profile answers, the evaluation areas picked (area only), and
  for each eligible mentor (Active, accepting new clients, with a login: the
  Assign list's rule) the profile lists, the three website texts, the date
  last given a new client and the room (decision 1, A). **No contact
  details**: no mentor email address, ``analysis.scrub`` on every free
  text, and the client's people's names (the primary contact's, as the
  engagement knows it) replaced by ``[name]`` in the client's own text.
* **The prompt is a versioned file** (BE9), ``match_prompts/<key>.v<n>.yaml``;
  every saved run names it.
* **Every run is kept** in the application database (decision 4, A,
  ``match_store``); the tab shows the latest.
* **A mentor at capacity is still sent**, marked, and may be suggested
  only when clearly the best fit (decision 2, rule 2 as drafted).

Dark behind ``MENTOR_MATCH`` (default off), read per request. It needs the
Anthropic integration and a key, not ``BUSINESS_EVALUATION``.
"""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

from core.branding import MODE_TEXT, render as render_branding
from core.espo import EspoError

from . import service
from .analysis import FALLBACK_BETA, questions_and_answers, scrub
from .surveys import PROFILE_KEY, Survey, latest

log = logging.getLogger("cbm_intake.evaluation.match")

PROMPT_DIR = Path(__file__).resolve().parent / "match_prompts"
MENTOR_PROFILE = "CMentorProfile"
MAX_TOKENS = 16000
MAX_SUGGESTIONS = 3
#: Characters kept from each website text, so one long write-up cannot
#: crowd out the roster. About 400 words.
TEXT_MAX = 2500

#: The descriptive fields sent for each mentor (decision 1, A), read only
#: when the CRM has them. The lists and capacity come from the Assign list's
#: own read (``assignments.service.list_eligible_mentors``).
TEXT_FIELDS = ("mentorTitle", "mentorSummary", "aboutMentor")
EXTRA_LIST_FIELDS = ("fluentLanguages",)


class MatchError(Exception):
    """A run that cannot be completed, with a message staff can read.
    ``cost`` is set when the AI service was called (and paid) first."""

    def __init__(self, message: str, *, cost: Optional[float] = None) -> None:
        super().__init__(message)
        self.cost = cost


# --- the structured reply ---------------------------------------------------------

class Suggestion(BaseModel):
    mentor_id: str = Field(description="The mentor's id exactly as given.")
    reason: str = Field(description="Two or three sentences: what in the mentor's "
                                    "profile fits what in the client's answers.")


class MatchReply(BaseModel):
    client_needs: str
    mentor_kind: str
    suggestions: list[Suggestion]
    points_to_check: list[str]


# --- the prompt file (BE9) ----------------------------------------------------------

@dataclass(frozen=True)
class Prompt:
    key: str
    version: int
    system: str

    @property
    def ref(self) -> str:
        return f"{self.key}.v{self.version}"


_NAME = re.compile(r"^([a-z0-9-]+)\.v(\d+)\.yaml$")


def load_prompts(directory: Path = PROMPT_DIR) -> dict[str, Prompt]:
    """Every mentor match prompt, keyed by version name. Raises
    ``MatchError`` on an invalid file."""
    out: dict[str, Prompt] = {}
    for path in sorted(directory.glob("*.yaml")):
        m = _NAME.match(path.name)
        if not m:
            raise MatchError(f"{path.name}: the file name must be <key>.v<n>.yaml")
        key, version = m.group(1), int(m.group(2))
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("key") != key or raw.get("version") != version:
            raise MatchError(f"{path.name}: key and version must match the file name")
        system = str(raw.get("system") or "").strip()
        if not system:
            raise MatchError(f"{path.name}: needs system text")
        out[f"{key}.v{version}"] = Prompt(key=key, version=version, system=system)
    return out


def current_prompt(prompts: Optional[dict[str, Prompt]] = None) -> Prompt:
    prompts = load_prompts() if prompts is None else prompts
    found = [p for p in prompts.values() if p.key == "mentor-match"]
    if not found:
        raise MatchError("There is no mentor match prompt file.")
    return max(found, key=lambda p: p.version)


# --- switches -----------------------------------------------------------------------

def switched_on(settings: Any) -> bool:
    """The tab and the routes exist."""
    return bool(getattr(settings, "mentor_match", False))


def ready_message(settings: Any) -> str:
    """Why a run cannot start, or "" when it can."""
    if not getattr(settings, "anthropic_in_use", False):
        return "The Anthropic integration is switched off in System Settings, so the AI analysis cannot run."
    if not (getattr(settings, "anthropic_api_key", "") or "").strip():
        return "No Anthropic API key is set in System Settings, so the AI analysis cannot run."
    return ""


# --- what is sent ----------------------------------------------------------------------

_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"</?(p|div|br|li|h[1-6]|tr)\b[^>]*>", re.IGNORECASE)
_SPACE = re.compile(r"[ \t\r\f\v]+")


def plain(value: Any, limit: int = TEXT_MAX) -> str:
    """A CRM text or wysiwyg value as plain text, scrubbed of contact
    details, cut at ``limit`` characters."""
    if not value:
        return ""
    text = _BLOCK.sub("\n", str(value))
    text = html.unescape(_TAG.sub("", text))
    lines = [_SPACE.sub(" ", ln).strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    text = scrub(text)
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + " …"
    return text


def _room(m: dict[str, Any]) -> dict[str, Any]:
    active, cap, avail = m.get("activeClients"), m.get("maxCapacity"), m.get("availableCapacity")
    if avail == -1 or cap == -1:
        return {"active_clients": active, "maximum_clients": "no limit",
                "available": "no limit", "at_capacity": False}
    return {"active_clients": active if active is not None else "unknown",
            "maximum_clients": cap if cap is not None else "not set",
            "available": avail if avail is not None else "unknown",
            "at_capacity": avail is not None and avail <= 0}


def mentor_entry(m: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """One mentor as sent. ``m`` is a row of the Assign list
    (``assignments.service._mentor_row``); ``extra`` the descriptive read.
    Never the mentor's email address."""
    entry: dict[str, Any] = {
        "id": m["id"],
        "name": m.get("name") or "",
        "areas_of_expertise": list(m.get("expertise") or []),
        "industries_served": list(m.get("industryExperience") or []),
        "industry_sector": m.get("industrySector") or "",
        "mentoring_focus_areas": list(m.get("focusAreas") or []),
        "years_of_experience": m.get("yearsOfExperience"),
        "mentor_type": m.get("mentorType") or "",
        "languages": list(extra.get("fluentLanguages") or []),
        "headline": plain(extra.get("mentorTitle"), 300),
        "website_summary": plain(extra.get("mentorSummary")),
        "website_about": plain(extra.get("aboutMentor")),
        "last_given_a_new_client": (m.get("lastClientAssigned") or "")[:10] or "not recorded",
    }
    entry.update(_room(m))
    return entry


def client_entry(eng: dict[str, Any], company: str,
                 profile: Optional[tuple[Survey, dict[str, Any]]],
                 areas: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "company": scrub(company or "") or "(not given)",
        "intake_focus_areas": list(eng.get("mentoringFocusAreas") or []),
        "intake_needs": plain(eng.get("mentoringNeedsDescription"), 6000) or "Not given",
    }
    if profile is not None:
        out["business_profile"] = questions_and_answers(*profile)
    else:
        out["business_profile"] = "The client has not answered the business profile survey."
    out["evaluation_areas_picked"] = areas or "None picked"
    company_name = out.pop("company")
    out = redact_names(out, people_names(eng, company))
    return {"company": company_name, **out}


def people_names(eng: dict[str, Any], company: str) -> list[str]:
    """The client's people's names known on the engagement: the primary
    contact, and the person part of the engagement's "Person — Company"
    name. Never the company's own name."""
    names: list[str] = []
    for raw in (eng.get("primaryEngagementContactName") or "",
                (eng.get("name") or "").split(" — ", 1)[0] if " — " in (eng.get("name") or "") else ""):
        raw = raw.strip()
        if raw and raw.lower() != (company or "").strip().lower() and raw not in names:
            names.append(raw)
    return names


def redact_names(value: Any, names: list[str]) -> Any:
    """Every string in ``value`` with the client's people's names (the full
    name, then each part of three letters or more) replaced by ``[name]``."""
    parts: list[str] = []
    for n in names:
        parts.append(n)
        parts += [w for w in re.split(r"\s+", n) if len(w) >= 3]
    if not parts:
        return value
    pattern = re.compile(r"\b(" + "|".join(re.escape(p) for p in parts) + r")\b", re.IGNORECASE)

    def walk(v: Any) -> Any:
        if isinstance(v, str):
            return pattern.sub("[name]", v)
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v

    return walk(value)


def user_message(client: dict[str, Any], mentors: list[dict[str, Any]]) -> str:
    return json.dumps({"client": client, "mentors": mentors}, ensure_ascii=False, indent=1)


# --- the reads ------------------------------------------------------------------------

async def _field_names(client: Any) -> set[str]:
    try:
        meta = await client.metadata(f"entityDefs.{MENTOR_PROFILE}.fields")
    except EspoError as exc:
        log.warning("mentor match: mentor field metadata not read: %s", exc)
        return set()
    return set(meta) if isinstance(meta, dict) else set()


async def mentor_extras(client: Any, ids: list[str]) -> dict[str, dict[str, Any]]:
    """The website texts and languages per mentor id, read as the staff
    member. A field the CRM lacks is not asked for; a failed read sends the
    lists only (logged)."""
    have = await _field_names(client)
    fields = [f for f in TEXT_FIELDS + EXTRA_LIST_FIELDS if f in have]
    if not fields or not ids:
        return {}
    out: dict[str, dict[str, Any]] = {}
    wanted = set(ids)
    try:
        # The Assign list's own filter, so one page covers the same mentors
        # (the list itself is one page of 200).
        page = await client.list(MENTOR_PROFILE, where=[
            {"type": "isTrue", "attribute": "acceptingNewClients"},
            {"type": "equals", "attribute": "mentorStatus", "value": "Active"}],
            select="id," + ",".join(fields), max_size=200)
        for r in page.get("list", []) or []:
            if r.get("id") in wanted:
                out[r["id"]] = r
    except EspoError as exc:
        log.warning("mentor match: mentor write-ups not read: %s", exc)
    return out


async def picked_areas(key_client: Any, engagement_id: str) -> list[str]:
    """The evaluation areas on the engagement, area only, under the org-wide
    key (as the Business profile tab reads them). Empty on any failure."""
    if key_client is None:
        return []
    from .sending import entity_available

    try:
        if not await entity_available(key_client):
            return []
        page = await key_client.list(service.ENTITY, where=[
            {"type": "equals", "attribute": "engagementId", "value": engagement_id}],
            select="id,evaluationArea", max_size=200)
    except EspoError as exc:
        log.warning("mentor match %s: areas not read: %s", engagement_id, exc)
        return []
    seen: list[str] = []
    for r in page.get("list", []) or []:
        a = r.get("evaluationArea") or ""
        if a and a not in seen:
            seen.append(a)
    return seen


def _profile(raw: str) -> Optional[tuple[Survey, dict[str, Any]]]:
    if not (raw or "").strip():
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        return None
    from .intake import _definitions

    surveys = _definitions()
    survey = surveys.get(data.get("survey") or "") or latest(surveys, PROFILE_KEY)
    return (survey, data["answers"]) if survey is not None else None


@dataclass
class Gathered:
    engagement: dict[str, Any]
    client: dict[str, Any]
    mentors: list[dict[str, Any]]
    notes: list[str] = field(default_factory=list)


async def gather(user_client: Any, key_client: Any, engagement_id: str) -> Gathered:
    """Everything a run sends. The staff member's own read of the engagement
    gates it (an ``EspoError`` there is the caller's to answer). Raises
    ``MatchError`` when the engagement already has a mentor or no mentor is
    eligible."""
    from assignments import service as assign_service

    eng = await user_client.get(service.ENGAGEMENT, engagement_id, select=(
        "name,engagementStatus,mentorProfileId,mentorProfileName,mentoringFocusAreas,"
        "mentoringNeedsDescription,engagementClientId,engagementClientName,"
        "primaryEngagementContactName"))
    if eng.get("mentorProfileId"):
        raise MatchError(
            f"This engagement is already assigned to {eng.get('mentorProfileName') or 'a mentor'}; "
            "the mentor match is for engagements waiting for a mentor.")
    notes: list[str] = []
    company = eng.get("engagementClientName") or ""
    profile = None
    if eng.get("engagementClientId"):
        try:
            prof = await user_client.get(service.CLIENT_PROFILE, eng["engagementClientId"],
                                         select="name,evaluationProfile")
            company = company or prof.get("name") or ""
            profile = _profile(prof.get("evaluationProfile") or "")
        except EspoError as exc:
            log.warning("mentor match %s: business profile not read: %s", engagement_id, exc)
            notes.append("The business profile could not be read with your access, so it was not sent.")
    roster = await assign_service.list_eligible_mentors(user_client)
    rows = roster.get("mentors") or []
    if not rows:
        raise MatchError("No mentor is Active, accepting new clients and linked to a login, "
                         "so there is no one to suggest.")
    if not roster.get("metricsAvailable"):
        notes.append("Mentors' client counts could not be read, so their room was sent as unknown.")
    extras = await mentor_extras(user_client, [r["id"] for r in rows])
    mentors = [mentor_entry(r, extras.get(r["id"], {})) for r in rows]
    areas = await picked_areas(key_client, engagement_id)
    return Gathered(engagement=eng, client=client_entry(eng, company, profile, areas),
                    mentors=mentors, notes=notes)


# --- the call --------------------------------------------------------------------------

@dataclass
class CallResult:
    reply: MatchReply
    model: str
    input_tokens: int
    output_tokens: int
    cost: float


async def call_claude(client: Any, model: str, system: str, message: str) -> CallResult:
    """One mentor match call. Raises ``MatchError`` on a refusal, a cut-off
    reply or a reply that does not fit; the SDK's own errors pass through."""
    resp = await client.beta.messages.parse(
        model=model,
        max_tokens=MAX_TOKENS,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        system=system,
        messages=[{"role": "user", "content": message}],
        output_format=MatchReply,
    )
    used = getattr(resp, "model", None) or model
    usage = getattr(resp, "usage", None)
    from enrichment.research import usage_cost

    cost, _ = usage_cost(usage, used)
    tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
    tokens_out = int(getattr(usage, "output_tokens", 0) or 0)
    log.info("mentor match call: model=%s input_tokens=%d output_tokens=%d cost=$%.4f",
             used, tokens_in, tokens_out, cost)
    if resp.stop_reason == "refusal":
        raise MatchError("The AI service declined to give a mentor match for this engagement.", cost=cost)
    if resp.stop_reason == "max_tokens":
        raise MatchError("The AI service's reply was cut off before it was complete.", cost=cost)
    parsed = getattr(resp, "parsed_output", None)
    if parsed is None:
        raise MatchError("The AI service's reply was not in the expected form.", cost=cost)
    return CallResult(reply=parsed, model=used, input_tokens=tokens_in,
                      output_tokens=tokens_out, cost=cost)


def _ids_to_names(by_id: dict[str, dict[str, Any]]):
    """A function replacing each mentor id in a text by the mentor's name;
    "Ann (s50)" and "(id: s50)" lose the id entirely."""
    if not by_id:
        return lambda text: text
    ids = "|".join(re.escape(i) for i in sorted(by_id, key=len, reverse=True))
    paren = re.compile(r"\s*\((?:id:?\s*)?(" + ids + r")\)")
    bare = re.compile(r"\b(" + ids + r")\b")

    def named(text: str) -> str:
        text = paren.sub("", text or "")
        return bare.sub(lambda m: by_id[m.group(1)]["name"] or m.group(1), text)

    return named


def shape_result(reply: MatchReply, mentors: list[dict[str, Any]],
                 notes: list[str]) -> dict[str, Any]:
    """The reply as stored and shown: each suggestion carries the mentor's
    name and room as sent. A suggestion naming a mentor who was not sent is
    dropped (and counted); repeats are dropped; at most three are kept."""
    by_id = {m["id"]: m for m in mentors}
    out, dropped, seen = [], 0, set()
    for s in reply.suggestions:
        m = by_id.get((s.mentor_id or "").strip())
        if m is None or m["id"] in seen:
            dropped += 1
            continue
        seen.add(m["id"])
        out.append({"mentorProfileId": m["id"], "name": m["name"], "reason": s.reason,
                    "activeClients": m["active_clients"], "maximumClients": m["maximum_clients"],
                    "available": m["available"], "atCapacity": m["at_capacity"]})
        if len(out) == MAX_SUGGESTIONS:
            break
    if dropped:
        log.warning("mentor match: %d suggestion(s) dropped (not in the list sent)", dropped)
    # The samples (11-19-26) named mentors by id in the text ("s50", or a CRM
    # id in production): every id sent is shown as the mentor's name.
    named = _ids_to_names(by_id)
    for s in out:
        s["reason"] = named(s["reason"])
    return {"clientNeeds": named(reply.client_needs), "mentorKind": named(reply.mentor_kind),
            "suggestions": out, "pointsToCheck": [named(p) for p in reply.points_to_check or []],
            "notes": notes, "mentorsSent": len(mentors), "dropped": dropped}


def system_text(prompt: Prompt, settings: Any) -> str:
    return render_branding(prompt.system, settings, MODE_TEXT)


async def run(settings: Any, *, user_client: Any, key_client: Any, claude: Any,
              engagement_id: str, prompts: Optional[dict[str, Prompt]] = None
              ) -> tuple[dict[str, Any], CallResult, Prompt]:
    """One run: gather, call, shape. Raises ``MatchError`` with a message
    staff can read; ``EspoError`` from the gating read passes through; an SDK
    error passes through for the caller to word."""
    msg = ready_message(settings)
    if msg:
        raise MatchError(msg)
    prompt = current_prompt(prompts)
    got = await gather(user_client, key_client, engagement_id)
    model = getattr(settings, "mentor_match_model", "") or "claude-opus-5-5"
    result = await call_claude(claude, model, system_text(prompt, settings),
                               user_message(got.client, got.mentors))
    return shape_result(result.reply, got.mentors, got.notes), result, prompt
