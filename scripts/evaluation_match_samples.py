"""Sample mentor matches from made-up clients (Business Evaluation phase 7,
stopping point (b); Doug's choice A, 11-19-26).

Two sets, each through the same code the application runs
(``evaluation/match.py``: what is sent, the prompt, the call, the shaping):

1. **The Association's real roster.** Four made-up clients against the
   mentors the Business Mentors Association's CRM lists as eligible (Active,
   accepting new clients, with a login), read with the applications' key.
   Read only: nothing is written to the CRM or the database.
2. **A made-up roster of 50 mentors**, written here, with no real data, to
   measure a Cleveland-sized run and to test the hard rules: the best fit at
   capacity, the best fit with a thin profile, a client nobody fits.

    PYTHONPATH=. uv run python scripts/evaluation_match_samples.py \
        --env-file ~/.config/cbm-bma/bma.env --out <folder>

Needs ``ANTHROPIC_API_KEY`` in ``.env``. Costs, by estimate, about $0.05 a run
on the Association's roster and $0.15 a run on the made-up 50: under $1 in all.
Writes one JSON file per run and ``samples.json`` (everything) to ``--out``.
``--dry-run`` reads the roster and prints the request sizes; no AI call.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import get_settings  # noqa: E402
from core.espo import EspoClient  # noqa: E402
from evaluation import match  # noqa: E402

PROFILE_KEY = "business-profile.v1"


def _profile(answers: dict[str, Any]):
    from evaluation.purpose import load_surveys

    return (load_surveys()[PROFILE_KEY], answers)


CLIENTS: dict[str, dict[str, Any]] = {
    "bakery": {
        "company": "Brightline Bakehouse",
        "contact": "Dana Testbaker",
        "focus": ["Financial Management", "Marketing"],
        "needs": "Dana Testbaker here. Our sales are good but cash runs out every month "
                 "before the wholesale cafés pay us. I want to understand my numbers "
                 "and plan for the holidays.",
        "areas": ["Finance"],
        "answers": {
            "what_you_sell": "Bread, pastries and cakes from our shop and wholesale to three cafés.",
            "industry": "Restaurant, café or food", "customer_type": "A mix of these",
            "where_you_sell": ["From a shop, office or location customers visit"],
            "stage": "Open 1 to 3 years", "people": 5, "owner_time": "Yes, full time",
            "revenue_range": "$100,000 to $250,000", "profitable": "About even",
            "goals": ["Get my finances organized", "Raise my prices or improve my margins"],
            "biggest_challenge": "Cash flow. The cafés pay 45 days late and flour costs went up.",
            "tried_already": "I asked the cafés to pay faster. One did.",
            "capacity": "1 to 3 hours"},
    },
    "software": {
        "company": "Ledgerline Apps",
        "contact": "Sam Coder",
        "focus": ["Funding", "Business Planning"],
        "needs": "Two founders building scheduling software for dental offices. We have "
                 "four paying pilots and want to raise a seed round or find a grant.",
        "areas": ["Funding", "Product"],
        "answers": {
            "what_you_sell": "Scheduling software sold by subscription to dental offices.",
            "industry": "Technology or software", "customer_type": "Other businesses",
            "where_you_sell": ["Online"], "stage": "Open less than a year", "people": 2,
            "owner_time": "Yes, full time", "revenue_range": "Under $25,000",
            "profitable": "No", "goals": ["Get a loan or other funding", "Get more customers"],
            "biggest_challenge": "We do not know whether to raise money or grow slowly.",
            "capacity": "More than 6 hours"},
    },
    "landscaping": {
        "company": "Verde Landscaping",
        "contact": "Luis Example",
        "focus": ["Operations", "Human Resources"],
        "needs": "Prefiero hablar en español. We have twelve seasonal workers and I spend "
                 "every evening on scheduling and payroll. I want systems so I can grow.",
        "areas": [],
        "answers": {
            "what_you_sell": "Lawn care and landscaping for homes and small offices.",
            "industry": "Construction or trades", "customer_type": "A mix of these",
            "where_you_sell": ["At the customer's home or site"], "stage": "Open more than 5 years",
            "people": 14, "owner_time": "Yes, full time", "revenue_range": "$500,000 to $1 million",
            "profitable": "Yes", "goals": ["Work fewer hours", "Hire my first employee or more staff"],
            "biggest_challenge": "Scheduling crews and payroll take all my evenings.",
            "capacity": "1 to 3 hours"},
    },
    "nofit": {
        "company": "Northcoast Vet Telehealth",
        "contact": "Pat Example",
        "focus": ["Legal", "International"],
        "needs": "We want to export a veterinary telemedicine service to Canada and need "
                 "help with cross-border veterinary licensing and medical data rules.",
        "areas": [],
        "answers": None,                                # the profile was not answered
    },
}

# --- the made-up roster of 50 (no real data) -----------------------------------------

_KINDS = [
    (["Finance", "Accounting"], ["Professional Services"], "Retired CPA; helped small firms with books and cash flow."),
    (["Marketing", "Sales"], ["Retail"], "Ran marketing for a regional retail chain."),
    (["Operations"], ["Manufacturing"], "Plant manager for twenty years."),
    (["Technology"], ["Technology or software"], "Built and sold a software company."),
    (["Human Resources"], ["Healthcare"], "HR director at a hospital system."),
    (["Legal"], ["Professional Services"], "Business lawyer, contracts and leases."),
    (["Funding", "Finance"], ["Banking"], "Commercial lender at a community bank."),
    (["Strategy"], ["Nonprofit"], "Executive director of two nonprofits."),
]
_FIRST = ["Alex", "Blair", "Casey", "Drew", "Emery", "Finley", "Gray", "Harper", "Indy", "Jordan"]
_LAST = ["Abbott", "Brooks", "Carver", "Dalton", "Ellis"]


def made_up_roster() -> list[dict[str, Any]]:
    rows = []
    for i in range(50):
        exp, ind, about = _KINDS[i % len(_KINDS)]
        active = i % 4
        rows.append({
            "id": f"s{i:02d}", "name": f"{_FIRST[i % 10]} {_LAST[i // 10]}",
            "expertise": exp, "industryExperience": ind, "industrySector": ind[0],
            "focusAreas": exp, "yearsOfExperience": 5 + i % 25, "mentorType": "Mentor",
            "lastClientAssigned": f"2026-{1 + i % 10:02d}-15", "activeClients": active,
            "maxCapacity": 3, "availableCapacity": 3 - active,
            "_extra": {"fluentLanguages": ["English"], "mentorTitle": exp[0] + " mentor",
                       "mentorSummary": about, "aboutMentor": f"<p>{about}</p>"}})
    # The rigged cases. s50: the bakery's ideal mentor, at capacity.
    rows.append({"id": "s50", "name": "Morgan Baker", "expertise": ["Finance"],
                 "industryExperience": ["Restaurant, café or food"], "industrySector": "Food",
                 "focusAreas": ["Cash flow", "Pricing"], "yearsOfExperience": 30,
                 "mentorType": "Mentor", "lastClientAssigned": "2026-11-01",
                 "activeClients": 3, "maxCapacity": 3, "availableCapacity": 0,
                 "_extra": {"fluentLanguages": ["English"], "mentorTitle": "Former bakery chain CFO",
                            "mentorSummary": "CFO of a 40-store bakery chain; fixed wholesale cash flow.",
                            "aboutMentor": "<p>Thirty years in food finance.</p>"}})
    # s51: Spanish-speaking trades mentor with a thin profile, with room.
    rows.append({"id": "s51", "name": "Rosa Thin", "expertise": ["Operations"],
                 "industryExperience": ["Construction or trades"], "industrySector": "",
                 "focusAreas": [], "yearsOfExperience": None, "mentorType": "Mentor",
                 "lastClientAssigned": None, "activeClients": 0, "maxCapacity": 2,
                 "availableCapacity": 2,
                 "_extra": {"fluentLanguages": ["English", "Spanish"], "mentorTitle": "",
                            "mentorSummary": "", "aboutMentor": ""}})
    return rows


def _entries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [match.mentor_entry(r, r.get("_extra", {})) for r in rows]


def _client(key: str) -> dict[str, Any]:
    c = CLIENTS[key]
    eng = {"name": f"{c['contact']} — {c['company']}", "primaryEngagementContactName": c["contact"],
           "mentoringFocusAreas": c["focus"], "mentoringNeedsDescription": f"<p>{c['needs']}</p>"}
    profile = _profile(c["answers"]) if c["answers"] else None
    return match.client_entry(eng, c["company"], profile, c["areas"])


async def association_roster(crm: Any) -> list[dict[str, Any]]:
    from assignments import service as assign_service

    roster = await assign_service.list_eligible_mentors(crm)
    rows = roster.get("mentors") or []
    extras = await match.mentor_extras(crm, [r["id"] for r in rows])
    return [match.mentor_entry(r, extras.get(r["id"], {})) for r in rows]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", required=True,
                        help="the Association's credential file, ~/.config/cbm-bma/bma.env")
    parser.add_argument("--out", required=True, help="folder for the results")
    parser.add_argument("--org", default="Business Mentors Association",
                        help="the organization's name filled into the prompt")
    parser.add_argument("--keep", action="store_true",
                        help="reuse a run already written to --out instead of paying for it again")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    from sandbox.targets import api_connection, resolve

    settings = get_settings()
    base, key, _ = api_connection(args.env_file)
    if resolve(base) is None:
        print(f"Refused: {base} is not a training system.")
        return 2
    crm = EspoClient(base, key, 60)
    real = await association_roster(crm)
    fake = _entries(made_up_roster())
    print(f"The Association's roster: {len(real)} eligible mentors. Made-up roster: {len(fake)}.")
    runs = ([("association", k, real) for k in CLIENTS]
            + [("made-up-50", k, fake) for k in ("bakery", "landscaping", "nofit")])
    prompt = match.current_prompt()
    system = match.system_text(prompt, settings.model_copy(
        update={"organization_name": args.org}))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.dry_run:
        for roster, client, mentors in runs:
            msg = match.user_message(_client(client), mentors)
            print(f"{roster} / {client}: {len(msg)} characters")
        return 0
    if not settings.anthropic_api_key:
        print("Missing in .env: ANTHROPIC_API_KEY")
        return 2
    import anthropic

    claude = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=180.0)
    results, total = [], 0.0
    for roster, client, mentors in runs:
        done = out / f"{roster}-{client}.json"
        if args.keep and done.exists():       # a run already made: kept, not paid for again
            row = json.loads(done.read_text(encoding="utf-8"))
            results.append(row)
            total += row.get("cost") or 0
            print(f"{roster} / {client}: kept from an earlier run")
            continue
        sent = _client(client)
        try:
            res = await match.call_claude(claude, settings.mentor_match_model, system,
                                          match.user_message(sent, mentors))
        except match.MatchError as exc:
            print(f"{roster} / {client}: {exc}")
            results.append({"roster": roster, "client": client, "error": str(exc)})
            continue
        shaped = match.shape_result(res.reply, mentors, [])
        total += res.cost
        row = {"roster": roster, "client": client, "sent_client": sent,
               "mentors_sent": len(mentors), "input_tokens": res.input_tokens,
               "output_tokens": res.output_tokens, "cost": round(res.cost, 4),
               "prompt": prompt.ref, "model": res.model, "result": shaped}
        results.append(row)
        (out / f"{roster}-{client}.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=1), encoding="utf-8")
        names = ", ".join(s["name"] + (" (at capacity)" if s["atCapacity"] else "")
                          for s in shaped["suggestions"])
        print(f"{roster} / {client}: ${res.cost:.3f}, {res.input_tokens} in: {names}")
    (out / "samples.json").write_text(json.dumps(results, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    print(f"Total ${total:.2f}. Written to {out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
