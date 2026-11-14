"""Make a Business Evaluation link for testing (phase 1, step 7).

Since phase 2 the Send Evaluation button in Client Management does this for
mentors; this script runs the same path (``evaluation/sending.send``) for a
test. Given an engagement and the evaluation areas, it creates one Business Evaluation record per area in the
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
from evaluation import sending  # noqa: E402
from evaluation.surveys import load_all  # noqa: E402
from surveys.store import SurveyStore  # noqa: E402


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
    try:
        chosen = sending.choose_areas(surveys, args.areas)
    except sending.SendError as exc:
        print(exc, file=sys.stderr)
        return 2

    client = EspoClient(settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds)
    store = SurveyStore(settings.database_url)
    try:
        if args.dry_run:
            ctx = await sending.engagement_context(client, args.engagement_id)
            round_no = sending.next_round(await sending.list_records(client, args.engagement_id))
            print(f"Engagement: {ctx['engagement'].get('name')}  ({ctx['company']})")
            print(f"Round {round_no}; business profile "
                  f"{'owed' if ctx['profileNeeded'] else 'already answered'}; "
                  f"areas: {', '.join(s.title for s in chosen)}")
            print("Dry run: nothing written.")
            return 0
        result = await sending.send(
            client, store, engagement_id=args.engagement_id, area_keys=args.areas,
            surveys=surveys, created_by=args.created_by, days=settings.evaluation_link_days)
    except sending.SendError as exc:
        print(exc, file=sys.stderr)
        return 2
    except EspoError as exc:
        print(f"The CRM refused: {exc}", file=sys.stderr)
        return 1
    finally:
        await store.dispose()

    print(f"Round {result['round']}; business profile "
          f"{'owed' if result['profileNeeded'] else 'already answered'}")
    for rec in result["records"]:
        print(f"  created Business Evaluation {rec['id']} ({rec['area']})")
    link = result["link"]
    base = (args.base_url or settings.app_base_url or "http://localhost:8000").rstrip("/")
    print(f"\nLink (expires {link['expires_at']:%Y-%m-%d %H:%M} UTC):\n{sending.link_url(base, link['token'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
