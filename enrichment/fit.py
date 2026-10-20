"""The fit score — pure functions, no CRM calls (design § 4, rulings E2, E12, E13).

The gate comes first. A lead whose location is confirmed outside the chapter's
counties scores 0 and is flagged *Out of area*; a lead whose only address is a
registered agent's is *Location unknown* and is scored on its signals; with no
service area set the gate is not applied and every lead reads *Passed*.

Then three signals, 0 to 100 each, averaged by the chapter's weights:

* **operating business** — a trade name rather than a holding or property
  company, not at a registered-agent address, a recent filing, not a serial
  filer's entity;
* **segment** — the chapter's segment list against the lead's industry and
  name; a fixed 50 while the list does not exist;
* **findability** — an email and a website held, or a website the free web
  check verified.

Every reason is one plain sentence, written to ``fitReasons``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Mapping, Optional

from . import geo
from .terms import Segments, Terms, core_name, matches, words

#: Bump when the scoring rules change: every lead is rescored.
RULE_VERSION = "1"

GATE_PASSED = "Passed"
GATE_UNKNOWN = "Location unknown"
GATE_OUT = "Out of area"

#: An associate named on at least this many filings is a serial filer.
SERIAL_FILER_MIN = 4

_ASSOCIATE_KEYS = ("associates", "associate", "incorporators", "incorporator",
                   "organizers", "organizer", "members")
_AGENT_NAME_KEYS = ("agent_name", "registered_agent", "registered_agent_name", "agent")
_AGENT_STREET_KEYS = ("agent_street", "agent_address", "registered_agent_address",
                      "agent_address_street")
_DATE_KEYS = ("effective_date", "filing_date", "date_filed", "filed", "formation_date")


@dataclass(frozen=True)
class WebCheck:
    """What the free web check found (``findability.check``)."""
    website: str = ""
    verified: bool = False
    evidence: str = ""


@dataclass(frozen=True)
class ScoreContext:
    area: frozenset[tuple[str, str]]
    terms: Terms
    segments: Segments = Segments()
    weights: tuple[float, float, float] = (1.0, 1.0, 1.0)
    serial_counts: Mapping[str, int] = field(default_factory=dict)
    today: date = field(default_factory=date.today)

    @property
    def version(self) -> str:
        """The rule version plus a short hash of everything a chapter can tune,
        so a change of weights, counties or lists rescores every lead. Fits the
        20-character field."""
        blob = json.dumps({
            "w": self.weights, "a": sorted(self.area),
            "t": [self.terms.holding_words, self.terms.trade_words, self.terms.agent_names,
                  self.terms.agent_streets, self.terms.legal_suffixes],
            "s": [self.segments.favoured, self.segments.excluded],
        }, sort_keys=True, default=list)
        return f"{RULE_VERSION}.{hashlib.sha1(blob.encode()).hexdigest()[:8]}"


@dataclass
class FitResult:
    score: int
    gate: str
    county: str
    operating: int
    segment: int
    findability: int
    reasons: list[str]
    #: A website the web check verified, for the sweep to write if empty (E14).
    verified_website: str = ""

    def payload(self, version: str, scored_at: str) -> dict[str, Any]:
        return {
            "fitScore": self.score, "fitGate": self.gate, "fitCounty": self.county or None,
            "fitOperating": self.operating, "fitSegment": self.segment,
            "fitFindability": self.findability, "fitReasons": "\n".join(self.reasons),
            "fitScoredAt": scored_at, "fitRuleVersion": version,
        }


def parse_weights(setting: str) -> tuple[float, float, float]:
    """``1,1,1`` → three non-negative weights; anything unreadable is 1,1,1."""
    try:
        parts = [max(0.0, float(p)) for p in (setting or "").split(",")]
    except ValueError:
        return (1.0, 1.0, 1.0)
    if len(parts) != 3 or sum(parts) == 0:
        return (1.0, 1.0, 1.0)
    return (parts[0], parts[1], parts[2])


def import_row(lead: Mapping[str, Any]) -> dict[str, Any]:
    raw = lead.get("importRow")
    if not raw:
        return {}
    try:
        row = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return {}
    if not isinstance(row, dict):
        return {}
    return {str(k).strip().lower().replace(" ", "_"): v for k, v in row.items()}


def _first(row: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return str(v).strip()
    return ""


def associates(lead: Mapping[str, Any]) -> list[str]:
    """The filing's associates from the import row, normalised; [] when the
    import carried none (build plan § 4)."""
    raw = _first(import_row(lead), _ASSOCIATE_KEYS)
    names = re.split(r"[;|\n]+|\s+and\s+", raw) if raw else []
    return [n for n in (" ".join(words(x).split()) for x in names) if n]


def _filing_date(row: Mapping[str, Any]) -> Optional[date]:
    raw = _first(row, _DATE_KEYS)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            continue
    return None


def at_agent_address(lead: Mapping[str, Any], terms: Terms) -> bool:
    """Whether the lead's mailing address is a registered-agent service's
    (E12: never a fact about the business)."""
    street = lead.get("mailingAddressStreet") or ""
    if street and matches(street, terms.agent_streets):
        return True
    row = import_row(lead)
    agent = _first(row, _AGENT_NAME_KEYS)
    agent_street = _first(row, _AGENT_STREET_KEYS)
    if agent and matches(agent, terms.agent_names) and agent_street and street:
        return words(agent_street) == words(street)
    return False


def _clamp(v: float) -> int:
    return int(max(0, min(100, round(v))))


def _gate(lead: Mapping[str, Any], ctx: ScoreContext, reasons: list[str]) -> tuple[str, str]:
    if not ctx.area:
        reasons.append("No service area is set, so the location was not checked.")
        return GATE_PASSED, ""
    if at_agent_address(lead, ctx.terms):
        reasons.append("The only address is a registered agent's, so the location is unknown.")
        return GATE_UNKNOWN, ""
    postal = lead.get("mailingAddressPostalCode") or ""
    counties = geo.counties_for(postal)
    if not counties:
        reasons.append("No usable postal code, so the location is unknown." if not geo.zip5(postal)
                       else f"Postal code {geo.zip5(postal)} is not in the county table, so the location is unknown.")
        return GATE_UNKNOWN, ""
    hit = geo.in_area(counties, ctx.area)
    if hit:
        reasons.append(f"Postal code {geo.zip5(postal)} is in {hit} County, inside the service area.")
        return GATE_PASSED, hit
    first = counties[0][1]
    reasons.append(f"Postal code {geo.zip5(postal)} is in {first} County, outside the service area.")
    return GATE_OUT, first


def _operating(lead: Mapping[str, Any], ctx: ScoreContext, gate_unknown_agent: bool,
               reasons: list[str]) -> int:
    name = lead.get("businessName") or lead.get("name") or ""
    v = 60.0
    holding = matches(name, ctx.terms.holding_words)
    trade = matches(name, ctx.terms.trade_words)
    if holding:
        v -= 40
        reasons.append(f"The name reads as a holding or property company ({', '.join(holding)}).")
    if trade:
        v += 25
        reasons.append(f"The name reads as a trade ({', '.join(trade)}).")
    if gate_unknown_agent:
        v -= 15
    filed = _filing_date(import_row(lead))
    if filed is not None:
        months = (ctx.today.year - filed.year) * 12 + (ctx.today.month - filed.month)
        if 0 <= months <= 18:
            v += 15
            reasons.append(f"Filed {filed.isoformat()}, within the last 18 months.")
        elif months > 60:
            v -= 10
            reasons.append(f"Filed {filed.isoformat()}, more than five years ago.")
    people = associates(lead)
    serial = [p for p in people if ctx.serial_counts.get(p, 0) >= SERIAL_FILER_MIN]
    if serial:
        v -= 30
        reasons.append(f"A serial filer is named on it ({serial[0]}, on "
                       f"{ctx.serial_counts[serial[0]]} filings).")
    elif not people and import_row(lead):
        reasons.append("The import carried no associates, so serial filers were not checked.")
    return _clamp(v)


def _segment(lead: Mapping[str, Any], ctx: ScoreContext, reasons: list[str]) -> int:
    if ctx.segments.empty:
        return 50
    text = " ".join(str(lead.get(k) or "") for k in ("industry", "businessName", "name"))
    bad = matches(text, ctx.segments.excluded)
    if bad:
        reasons.append(f"Its industry is one the chapter does not serve ({bad[0]}).")
        return 10
    good = matches(text, ctx.segments.favoured)
    if good:
        reasons.append(f"Its industry is one the chapter serves well ({good[0]}).")
        return 85
    return 50


def _findability(lead: Mapping[str, Any], web: Optional[WebCheck], reasons: list[str]) -> tuple[int, str]:
    has_email = bool((lead.get("email") or "").strip())
    has_site = bool((lead.get("website") or "").strip())
    verified = web.website if web and web.verified else ""
    if verified and not has_site:
        reasons.append(f"Website {verified} verified: {web.evidence}.")
    elif verified and has_site and words(verified) != words(lead.get("website") or ""):
        reasons.append(f"A different website, {verified}, was verified ({web.evidence}); "
                       f"the stored one was kept.")
    site = has_site or bool(verified)
    if has_email and site:
        return 100, verified
    if has_email or site:
        return 50, verified
    reasons.append("No website or email was found.")
    return 0, verified


def score_lead(lead: Mapping[str, Any], ctx: ScoreContext,
               web: Optional[WebCheck] = None) -> FitResult:
    reasons: list[str] = []
    gate, county = _gate(lead, ctx, reasons)
    if gate == GATE_OUT:
        return FitResult(0, gate, county, 0, 0, 0, reasons)
    agent = gate == GATE_UNKNOWN and at_agent_address(lead, ctx.terms)
    operating = _operating(lead, ctx, agent, reasons)
    segment = _segment(lead, ctx, reasons)
    findability, verified = _findability(lead, web, reasons)
    w = ctx.weights
    score = _clamp((operating * w[0] + segment * w[1] + findability * w[2]) / sum(w))
    return FitResult(score, gate, county, operating, segment, findability, reasons,
                     verified_website=verified if not (lead.get("website") or "").strip() else "")
