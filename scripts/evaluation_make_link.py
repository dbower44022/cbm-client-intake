"""Make a Business Evaluation link for testing (phase 1, step 7).

Phase 2 replaces this with the Send Evaluation button. Given an engagement and
the evaluation areas, it creates one Business Evaluation record per area in the
CRM (status Sent, the engagement's assigned users, the next round), makes the
link in the application database, and prints the link's address. Nothing is
emailed.

    PYTHONPATH=. uv run python scripts/evaluation_make_link.py <engagement id> finance marketing

Runs under the org-wide API key from ``.env`` (``ESPO_BASE_URL`` /
``ESPO_API_KEY``) against the database in ``DATABASE_URL``, which must be
migrated to head. ``--base-url`` sets the address printed (default
``APP_BASE_URL``, else http://localhost:8000). ``--dry-run`` reads and says
what it would do, writing nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import get_settings  # noqa: E402
from core.espo import EspoClient, EspoError  # noqa: E402
from evaluation import service  # noqa: E402
from evaluation.store import EvaluationStore  # noqa: E402
from evaluation.surveys import PROFILE_KEY, latest, load_all  # noqa: E402

ENGAGEMENT = "CEngagement"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("engagement_id")
    parser.add_argument("areas", nargs="+", help="survey keys, such as finance marketing")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--created-by", default="scripts/evaluation_make_link.py")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if settings.espo_dry_run or not settings.espo_api_key:
        print("This needs a real CRM: set ESPO_DRY_RUN=false and ESPO_API_KEY.", file=sys.stderr)
        return 2
    if not settings.store_enabled:
        print("This needs the application database: set DATABASE_URL.", file=sys.stderr)
        return 2

    surveys = load_all()
    chosen = []
    for key in dict.fromkeys(args.areas):
        survey = latest(surveys, key)
        if survey is None or key == PROFILE_KEY:
            known = sorted({s.key for s in surveys.values() if s.key != PROFILE_KEY})
            print(f"'{key}' is not an evaluation area here. Known: {', '.join(known)}", file=sys.stderr)
            return 2
        chosen.append(survey)
    profile_survey = latest(surveys, PROFILE_KEY)

    client = EspoClient(settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds)
    try:
        eng = await client.get(ENGAGEMENT, args.engagement_id,
                               select="name,engagementClientId,clientOrganizationName,assignedUsersIds")
        profile_id = eng.get("engagementClientId")
        if not profile_id:
            print(f"Engagement {eng.get('name')!r} has no client profile.", file=sys.stderr)
            return 2
        prof = await client.get(service.CLIENT_PROFILE, profile_id,
                                select="name,linkedCompanyName,evaluationProfile")
        company = (eng.get("clientOrganizationName") or prof.get("linkedCompanyName")
                   or prof.get("name") or "")
        earlier = await client.list(service.ENTITY, where=[
            {"type": "equals", "attribute": "engagementId", "value": args.engagement_id}],
            select="evaluationRound", max_size=200)
        round_no = 1 + max([r.get("evaluationRound") or 0 for r in earlier.get("list", [])] or [0])
        profile_needed = not (prof.get("evaluationProfile") or "").strip()

        print(f"Engagement: {eng.get('name')}  ({company})")
        print(f"Round {round_no}; business profile {'owed' if profile_needed else 'already answered'}; "
              f"areas: {', '.join(s.title for s in chosen)}")
        if args.dry_run:
            print("Dry run: nothing written.")
            return 0

        now = service.utcnow()
        made = []
        for survey in chosen:
            rec = await client.create(service.ENTITY, {
                "name": f"{survey.area} — {company}",
                "engagementId": args.engagement_id,
                "clientProfileId": profile_id,
                "evaluationArea": survey.area,
                "evaluationRound": round_no,
                "status": "Sent",
                "sentAt": service.crm_stamp(now),
                "surveyVersion": survey.ref,
                "assignedUsersIds": list(eng.get("assignedUsersIds") or []),
            })
            made.append((survey.key, survey.ref, rec["id"]))
            print(f"  created Business Evaluation {rec['id']} ({survey.area})")
    except EspoError as exc:
        print(f"The CRM refused: {exc}", file=sys.stderr)
        return 1

    rows = ([(PROFILE_KEY, profile_survey.ref, None)] if profile_needed else []) + made
    store = EvaluationStore(settings.database_url)
    link = await store.create_link(
        engagement_id=args.engagement_id, client_profile_id=profile_id, round_no=round_no,
        area_keys=[s.key for s in chosen], profile_needed=profile_needed, company_name=company,
        created_by=args.created_by, days=settings.evaluation_link_days, surveys=rows, now=now)
    await store.dispose()
    base = (args.base_url or settings.app_base_url or "http://localhost:8000").rstrip("/")
    print(f"\nLink (expires {link['expires_at']:%Y-%m-%d %H:%M} UTC):\n{base}/evaluation/{link['token']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
