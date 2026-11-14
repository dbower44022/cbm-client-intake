"""Sample Business Evaluation reports from made-up answers (phase 3,
stopping point (b)).

On one engagement this script runs, in order, the same code the
application runs:

1. **Send** (``evaluation/sending.send``): a new round with Finance and
   Marketing records, status Sent, and a link in the application database.
   Nothing is emailed.
2. **Submit** (``evaluation/service.deliver``): the made-up answers below
   are written to the CRM as the client's, the business profile to the
   client profile when it has none yet, each area record set to Submitted.
3. **Analyze** (``evaluation/analysis.run_analysis_cycle``): one Claude API
   call per area writes the draft report and sets Draft Ready. No email.

Then open the engagement as its mentor, on the Evaluations tab, and read
the two drafts. The answers describe a made-up bakery; one free-text answer
carries a phone number and an email address, to show they are removed
before the Claude API sees them.

    PYTHONPATH=. uv run python scripts/evaluation_sample_reports.py <engagement id>

Needs, in ``.env`` or the environment: ``ESPO_BASE_URL`` / ``ESPO_API_KEY``
(the org-wide key; the CRM must not be production), ``DATABASE_URL``
migrated to head, ``ANTHROPIC_API_KEY``. Costs about $0.10 to $0.20 per
area. ``--dry-run`` says what it would do and writes nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import get_settings  # noqa: E402
from core.espo import EspoClient, EspoError  # noqa: E402
from evaluation import analysis, sending, service  # noqa: E402
from evaluation.surveys import PROFILE_KEY, load_all  # noqa: E402
from surveys.store import SurveyStore  # noqa: E402

PROFILE = {
    "what_you_sell": ("Fresh bread, pastries and celebration cakes, sold from our shop to "
                      "neighbourhood customers and wholesale to three local cafés. "
                      "Orders: call 216-555-0187 or write orders@brightline.example."),
    "industry": "Restaurant, café or food",
    "customer_type": "A mix of these",
    "where_you_sell": ["From a shop, office or location customers visit",
                       "Through other stores or distributors"],
    "stage": "Open 1 to 3 years",
    "people": 5,
    "owner_time": "Yes, full time",
    "revenue_range": "$100,000 to $250,000",
    "profitable": "About even",
    "goals": ["Raise my prices or improve my margins", "Pay myself a regular wage",
              "Get more customers"],
    "biggest_challenge": ("Flour, butter and eggs have gone up a lot and I haven't changed "
                          "my prices. We are busy but there is never money left at the end "
                          "of the month."),
    "tried_already": "I cut the opening hours on Mondays to save on wages.",
    "capacity": "1 to 3 hours",
}

FINANCE = {
    "bookkeeping_method": "A spreadsheet",
    "separate_account": "Yes",
    "review_frequency": "Every few months",
    "accountant": "Yes, only for taxes",
    "confidence": 2,
    "top_customer_share": "A tenth to a quarter",
    "seasonality": "Yes, a lot",
    "paid_when": "It varies a lot",
    "pricing_basis": "I matched what competitors charge",
    "last_price_change": "More than 3 years ago",
    "biggest_costs": ["Materials, stock or ingredients", "Wages", "Rent or a place to work"],
    "cash_runway": "Less than a month",
    "cash_shortfall": "Once or twice",
    "debt": ["A credit card balance carried month to month", "An SBA or other government loan"],
    "owner_pay": "Yes, when there is money left over",
    "budget": "Only in my head",
    "finance_worry": ("January and February are slow and I had to put the flour order on "
                      "the credit card last winter. The cafés pay me when they feel like it."),
}

MARKETING = {
    "ideal_customer": ("People who live within a mile or two and want good bread every week, "
                       "and parents ordering birthday cakes."),
    "why_choose_you": "Everything is baked fresh each morning, and our sourdough is the best around.",
    "asked_customers": "Yes, once or twice",
    "repeat_customers": "Most of them",
    "how_found": ["Walking or driving past", "Word of mouth or referrals", "Social media"],
    "online_presence": ["A Google Business Profile", "An Instagram account", "A Facebook page"],
    "posting_frequency": "Now and then",
    "reviews": "11 to 50",
    "customer_list": "No",
    "monthly_spend": "Under $100",
    "weekly_hours": "Less than 2",
    "tracks_results": "I have a good idea",
    "marketing_confidence": 3,
    "marketing_goal": "Get more cake orders. They are where the money is.",
}

ANSWERS = {PROFILE_KEY: PROFILE, "finance": FINANCE, "marketing": MARKETING}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("engagement_id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if "crm-test" not in settings.espo_base_url and "localhost" not in settings.espo_base_url:
        print("Refused: ESPO_BASE_URL is not crm-test. Sample reports are made only there.")
        return 2
    missing = [n for n, v in (("ESPO_API_KEY", settings.espo_api_key),
                              ("DATABASE_URL", settings.database_url),
                              ("ANTHROPIC_API_KEY", settings.anthropic_api_key)) if not v]
    if missing:
        print("Missing in .env: " + ", ".join(missing))
        return 2
    surveys = load_all()
    crm = EspoClient(settings.espo_base_url, settings.espo_api_key,
                     max(settings.request_timeout_seconds, 60))
    if args.dry_run:
        ctx = await sending.engagement_context(crm, args.engagement_id)
        print(f"Would send Finance and Marketing to {ctx['company']}, answer them with "
              f"the made-up bakery answers (business profile "
              f"{'too' if ctx['profileNeeded'] else 'already answered, kept'}), and "
              "write two draft reports.")
        return 0
    store = SurveyStore(settings.database_url)
    try:
        sent = await sending.send(crm, store, engagement_id=args.engagement_id,
                                  area_keys=["finance", "marketing"], surveys=surveys,
                                  created_by="scripts/evaluation_sample_reports.py",
                                  days=settings.evaluation_link_days)
        link = sent["link"]
        print(f"1. Sent round {sent['round']} to {sent['company']}.")
        now = service.utcnow()
        await store.set_consent(link["id"], now)
        for row in await store.answers_for(link["id"]):
            key = row["survey_key"]
            survey = surveys.get(row["survey_version"]) or surveys[f"{key}.v1"]
            # As the page does: lock the answers in the application database,
            # write them to the CRM, and mark them delivered, so the engine's
            # retry pass never writes them again.
            saved = await store.submit(link["id"], key, ANSWERS[key],
                                       f"sample-{row['id']}", now)
            await service.deliver(crm, {**link, "consent_at": now}, saved, survey)
            await store.mark_delivered(saved["id"], now)
            print(f"2. Submitted {survey.title} with the made-up answers.")
        import anthropic

        claude = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key,
                                          timeout=600.0, max_retries=2)
        try:
            counts = await analysis.run_analysis_cycle(settings, crm, claude, surveys=surveys)
        finally:
            await claude.close()
        print(f"3. Analysis: {counts['ready']} draft ready, {counts['failed']} failed, "
              f"{counts['waiting']} waiting. The cost of each call is in the log above.")
        print("The link was not emailed. Use Expire on the Evaluations tab when done.")
        return 0 if counts["failed"] == 0 and counts["crmErrors"] == 0 else 1
    except (EspoError, sending.SendError) as exc:
        print(f"Stopped: {exc}")
        return 1
    finally:
        await store.dispose()


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(asyncio.run(main()))
