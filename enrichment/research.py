"""The AI research pass — one business at a time (build plan phase 2 § 4.1).

The request carries only what ruling E7 allows: the business name, its
address and any website, and for a lead the associates named on its public
filing. Never an email, phone, note, survey answer or a person's name a client
gave us.

The model searches the web (server-side web search and web fetch), then
reports through one tool, ``report_findings``, whose schema is strict. For
every candidate it lists which facts it SAW on the source page. The
application, not the model, counts them under ruling E12:

* **Verified** — the name AND at least one of: the street address, the postal
  code, an associate named on the filing. The address facts do not count when
  the lead's only address is a registered agent's.
* **Likely** — the name and the city only.
* **Unverified** — the name alone, or nothing.

A model that calls something verified on one fact gets Likely or Unverified,
whatever it says. An exact name in a registry and the owner's other business
are excluded by the instructions and, failing that, by the counting: a page
that shows only the name is never Verified.

Cost is computed from the response's own usage (tokens at the model's price,
plus $0.01 a web search) so the budget is real money, not an estimate.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger("cbm_intake.enrichment.research")

#: Dollars per million tokens (input, output, cache read), from Anthropic's
#: published prices (cached 10-06-26). A model not listed is priced as Opus.
PRICES: dict[str, tuple[float, float, float]] = {
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-opus-5": (5.0, 25.0, 0.50),
    "claude-opus-4-8": (5.0, 25.0, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-fable-5-1": (10.0, 50.0, 0.25),
}
WEB_SEARCH_COST = 0.01
FALLBACK_BETA = "server-side-fallback-2026-07-01"

FACT_NAME = "name"
FACT_STREET = "street_address"
FACT_POSTAL = "postal_code"
FACT_ASSOCIATE = "associate"
FACT_CITY = "city"
FACTS = (FACT_NAME, FACT_STREET, FACT_POSTAL, FACT_ASSOCIATE, FACT_CITY)
FACT_WORDS = {FACT_NAME: "the name", FACT_STREET: "the street address", FACT_POSTAL: "the postal code",
              FACT_ASSOCIATE: "an associate on the filing", FACT_CITY: "the city"}

VERIFIED, LIKELY, UNVERIFIED = "Verified", "Likely", "Unverified"
KINDS = ("website", "email", "phone", "industry")

_FACTS_SCHEMA = {"type": "array", "items": {"type": "string", "enum": list(FACTS)}}
REPORT_TOOL = {
    "name": "report_findings",
    "description": (
        "Report what you found about the business, once, at the end of your research. "
        "List every candidate value with the page it came from and exactly which facts "
        "about THIS business you saw on that page."),
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["business_found", "candidates", "people", "summary", "summary_sources"],
        "properties": {
            "business_found": {"type": "boolean"},
            "candidates": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["kind", "value", "source_url", "facts_seen"],
                "properties": {
                    "kind": {"type": "string", "enum": list(KINDS)},
                    "value": {"type": "string"},
                    "source_url": {"type": "string"},
                    "facts_seen": _FACTS_SCHEMA,
                }}},
            "people": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["name", "title", "email", "source_url", "facts_seen"],
                "properties": {
                    "name": {"type": "string"}, "title": {"type": "string"},
                    "email": {"type": "string"}, "source_url": {"type": "string"},
                    "facts_seen": _FACTS_SCHEMA,
                }}},
            "summary": {"type": "string"},
            "summary_sources": {"type": "array", "items": {"type": "string"}},
        },
    },
}

SYSTEM = """You research one small business for a nonprofit that mentors small businesses.
Find its own website, a general business email, its business phone, its industry, the
people who own or run it, and write a short factual summary of what it does.

The hard part is that most businesses share their name with others. Research on new
filings found that 97% of name matches were a DIFFERENT business. So:
- For every value you report, say exactly which facts about THIS business you saw on
  the source page: its name, its street address, its postal code, the name of an
  associate listed below, or only its city. Report only what the page actually shows.
- Never report a value from a business with a similar name somewhere else.
- A listing in a public registry that matches only the name is not evidence.
- If an associate owns or runs a DIFFERENT business, that business's details are not
  this business's details. Do not report them.
- If you cannot find the business, say business_found = false and report nothing.
- For industry, choose the closest value from the allowed list, or report none.
- People: only people the source shows owning or running THIS business, with their
  title. Report a person's email only if the page shows it as theirs.
- The summary: two to four plain sentences on what the business does, where, and its
  apparent stage. No praise, no guesses. Empty if business_found is false.
Search efficiently. When done, call report_findings exactly once."""


@dataclass
class Subject:
    """What E7 lets a run send about one business."""
    name: str
    street: str = ""
    city: str = ""
    state: str = ""
    postal: str = ""
    website: str = ""
    associates: list[str] = field(default_factory=list)
    agent_address: bool = False
    industry_options: list[str] = field(default_factory=list)

    def prompt(self) -> str:
        lines = [f"Business name: {self.name}"]
        address = ", ".join(p for p in (self.street, self.city, self.state, self.postal) if p)
        if address:
            lines.append(f"Address on record: {address}"
                         + (" (a registered agent's address, not the business's own)" if self.agent_address else ""))
        if self.website:
            lines.append(f"Website on record (confirm or correct it): {self.website}")
        if self.associates:
            lines.append("Associates named on its public filing: " + "; ".join(self.associates))
        if self.industry_options:
            lines.append("Allowed industry values: " + " | ".join(o for o in self.industry_options if o))
        return "\n".join(lines)


@dataclass
class Candidate:
    kind: str
    value: str
    source_url: str
    facts: list[str]
    confidence: str


@dataclass
class Person:
    name: str
    title: str
    email: str
    source_url: str
    facts: list[str]
    confidence: str


@dataclass
class Result:
    ok: bool
    found: bool = False
    candidates: list[Candidate] = field(default_factory=list)
    people: list[Person] = field(default_factory=list)
    summary: str = ""
    summary_sources: list[str] = field(default_factory=list)
    cost: float = 0.0
    model: str = ""
    searches: int = 0
    error: str = ""


def confidence(facts: list[str], *, agent_address: bool) -> str:
    """Ruling E12, counted by the application."""
    seen = set(facts or ())
    if agent_address:   # E12: an agent's address is never a fact about the business
        seen -= {FACT_STREET, FACT_POSTAL}
    if FACT_NAME not in seen:
        return UNVERIFIED
    if seen & {FACT_STREET, FACT_POSTAL, FACT_ASSOCIATE}:
        return VERIFIED
    if FACT_CITY in seen:
        return LIKELY
    return UNVERIFIED


def facts_text(facts: list[str]) -> str:
    return "\n".join(FACT_WORDS.get(f, f) for f in facts)


def usage_cost(usage: Any, model: str) -> tuple[float, int]:
    """Dollars and web searches for one response's usage."""
    if usage is None:
        return 0.0, 0
    price_in, price_out, price_cache = PRICES.get(model, PRICES["claude-opus-5-5"])
    get = (lambda k: getattr(usage, k, None) or 0) if not isinstance(usage, dict) else (lambda k: usage.get(k) or 0)
    tokens_in = get("input_tokens") + get("cache_creation_input_tokens") * 1.25
    cost = (tokens_in * price_in + get("output_tokens") * price_out
            + get("cache_read_input_tokens") * price_cache) / 1_000_000
    stu = getattr(usage, "server_tool_use", None) if not isinstance(usage, dict) else usage.get("server_tool_use")
    searches = 0
    if stu is not None:
        searches = int((getattr(stu, "web_search_requests", None) if not isinstance(stu, dict)
                        else stu.get("web_search_requests")) or 0)
    return cost + searches * WEB_SEARCH_COST, searches


def parse_report(raw: dict[str, Any], *, agent_address: bool, industry_options: list[str]) -> Result:
    res = Result(ok=True, found=bool(raw.get("business_found")))
    if not res.found:
        return res
    seen: set[tuple[str, str]] = set()
    for c in raw.get("candidates") or []:
        kind, value = str(c.get("kind") or ""), str(c.get("value") or "").strip()
        if kind not in KINDS or not value or (kind, value.lower()) in seen:
            continue
        if kind == "industry" and industry_options and value not in industry_options:
            continue   # not one of the CRM's options: it could never be written
        seen.add((kind, value.lower()))
        facts = [f for f in (c.get("facts_seen") or []) if f in FACTS]
        res.candidates.append(Candidate(kind, value, str(c.get("source_url") or ""), facts,
                                        confidence(facts, agent_address=agent_address)))
    for p in raw.get("people") or []:
        name = str(p.get("name") or "").strip()
        if not name:
            continue
        facts = [f for f in (p.get("facts_seen") or []) if f in FACTS]
        res.people.append(Person(name, str(p.get("title") or "").strip(), str(p.get("email") or "").strip(),
                                 str(p.get("source_url") or ""), facts, confidence(facts, agent_address=agent_address)))
    res.summary = str(raw.get("summary") or "").strip()
    res.summary_sources = [s for s in (raw.get("summary_sources") or []) if isinstance(s, str)][:8]
    return res


def _block_dict(block: Any) -> dict[str, Any]:
    return block.model_dump(exclude_none=True) if hasattr(block, "model_dump") else dict(block)


async def research(client: Any, subject: Subject, *, model: str, max_searches: int,
                   fallback: bool, record_cap: float, max_turns: int = 6) -> Result:
    """Research one business. Never raises for an API problem: a failed result
    carries the reason and whatever the calls cost."""
    tools = [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": max(1, int(max_searches))},
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": max(1, int(max_searches)) * 2},
        REPORT_TOOL,
    ]
    messages: list[dict[str, Any]] = [{"role": "user", "content": subject.prompt()}]
    total, searches, used_model = 0.0, 0, model
    nudged = False
    for _ in range(max_turns):
        kwargs: dict[str, Any] = dict(model=model, max_tokens=16000, system=SYSTEM, tools=tools,
                                      tool_choice={"type": "auto"}, messages=list(messages),
                                      output_config={"effort": "medium"})
        try:
            if fallback:
                resp = await client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            else:
                resp = await client.messages.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 — every API failure is a failed record, never a crash
            return Result(ok=False, cost=total, searches=searches, model=used_model,
                          error=f"{type(exc).__name__}: {str(exc)[:300]}")
        used_model = getattr(resp, "model", None) or model
        cost, n = usage_cost(getattr(resp, "usage", None), used_model)
        total += cost
        searches += n
        stop = getattr(resp, "stop_reason", None)
        if stop == "refusal":
            return Result(ok=False, cost=total, searches=searches, model=used_model,
                          error="The AI model declined to research this business.")
        for block in resp.content or []:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == REPORT_TOOL["name"]:
                raw = block.input if isinstance(block.input, dict) else json.loads(block.input or "{}")
                res = parse_report(raw, agent_address=subject.agent_address,
                                   industry_options=subject.industry_options)
                res.cost, res.searches, res.model = total, searches, used_model
                return res
        if total > record_cap:
            return Result(ok=False, cost=total, searches=searches, model=used_model,
                          error=f"Stopped: this business had cost ${total:.2f}, over the "
                                f"${record_cap:.2f} limit per business.")
        messages.append({"role": "assistant", "content": [_block_dict(b) for b in resp.content or []]})
        if stop == "pause_turn":
            continue   # the server resumes its own search loop
        if nudged:
            break
        nudged = True
        messages.append({"role": "user", "content": "Call report_findings now with what you found."})
    return Result(ok=False, cost=total, searches=searches, model=used_model,
                  error="The AI model finished without reporting its findings.")
