"""Probe the Fathom API with an individual (or team) key — Phase 0/3 checks.

READ-ONLY by default: lists what the key can see, and (--match) which
crm-test candidate sessions would pair with which Fathom meetings, without
writing anything anywhere. The one write path is explicit:
``--deliver SESSION_ID`` runs the real fetch + write-back for exactly that
session (transcript / doc link / AI summary / action-items routing), which
is the live verification step from prds/fathom-transcript-integration.md.

Usage (key never goes on the command line by default — export it):

    export FATHOM_API_KEY=...           # an individual key is fine for testing:
                                        # it sees that user's own recordings
                                        # plus anything shared to their Team
    uv run python scripts/probe_fathom.py                # list meetings (14 days)
    uv run python scripts/probe_fathom.py --days 30      # wider window
    uv run python scripts/probe_fathom.py --match        # + pair with CRM sessions
    uv run python scripts/probe_fathom.py --deliver <id> # WRITE one session

The CRM side comes from the usual env/.env (ESPO_BASE_URL / ESPO_API_KEY —
defaults to crm-test).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import Settings  # noqa: E402
from core.espo import EspoClient  # noqa: E402
from core.fathom import DEFAULT_BASE_URL, FathomClient, normalize_meeting_url  # noqa: E402
from sessions.config import AI_SUMMARY_FIELD, SESSION, TRANSCRIPT_DOC_URL_FIELD  # noqa: E402
from sessions.transcripts import (  # noqa: E402
    FathomTranscriptSource,
    _candidate_sessions,
    _write_back,
)


def _fmt(stamp: object) -> str:
    return str(stamp or "—")


async def list_meetings(client: FathomClient, days: int) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    meetings = await client.list_meetings(since)
    print(f"\nFathom meetings visible to this key since {since:%Y-%m-%d} "
          f"({len(meetings)}):\n")
    for m in meetings:
        key = normalize_meeting_url(m.get("meeting_url"))
        summary = m.get("summary")
        items = m.get("action_items")
        print(f"- {m.get('title') or m.get('meeting_title') or '(untitled)'}")
        print(f"    recording_id: {_fmt(m.get('recording_id') or m.get('id'))}"
              f"   recorded_by: {_fmt((m.get('recorded_by') or {}).get('email'))}")
        print(f"    start: {_fmt(m.get('recording_start_time') or m.get('scheduled_start_time'))}")
        print(f"    meeting_url: {_fmt(m.get('meeting_url'))}")
        print(f"    normalized key: {key or 'UNRECOGNIZED (no correlation possible)'}")
        print(f"    share_url: {_fmt(m.get('share_url'))}")
        print(f"    summary: {'yes' if summary else 'no'}   "
              f"action items: {len(items) if isinstance(items, list) else 'no'}")
    if not meetings:
        print("  (none — check the key, the window, or whether this account "
              "has recordings)")
    return meetings


async def match_sessions(settings: Settings, espo: EspoClient,
                         source: FathomTranscriptSource) -> None:
    now = datetime.now(timezone.utc)
    candidates = await _candidate_sessions(settings, espo, now, any_link=True)
    print(f"\nCRM candidate sessions (past, linked, no transcript yet, last "
          f"{settings.transcript_give_up_days} days): {len(candidates)}\n")
    for session in candidates:
        link = session.get("videoMeetingLink") or ""
        if not source.matches(link):
            print(f"- {session['id']}  {session.get('name')}: link not "
                  f"recognizable ({link or 'none'})")
            continue
        result = await source.fetch(session, "")  # read-only: no writes here
        extra = ""
        if result.status == "ready":
            extra = (f" — transcript {len(result.html)} chars"
                     f"{', summary' if result.summary_html else ''}"
                     f"{', action items' if result.action_items_html else ''}")
        print(f"- {session['id']}  {session.get('name')} "
              f"[{_fmt(session.get('dateStart'))}]: {result.status}"
              f"{' (' + result.reason + ')' if result.reason else ''}{extra}")
    if not candidates:
        print("  (none — create a past Scheduled session with the meeting's "
              "link to test matching)")


async def deliver_one(settings: Settings, espo: EspoClient,
                      source: FathomTranscriptSource, session_id: str) -> None:
    fields = await espo.metadata(f"entityDefs.{SESSION}.fields")
    session = await espo.get(
        SESSION, session_id,
        select="id,name,dateStart,videoMeetingLink,nextSteps",
    )
    result = await source.fetch(session, "")
    print(f"\nfetch for {session_id} ({session.get('name')}): {result.status} "
          f"{result.reason}")
    if result.status != "ready":
        return
    await _write_back(
        espo, session, result,
        TRANSCRIPT_DOC_URL_FIELD in fields, AI_SUMMARY_FIELD in fields,
    )
    stored = await espo.get(
        SESSION, session_id,
        select=f"id,nextSteps,{TRANSCRIPT_DOC_URL_FIELD},{AI_SUMMARY_FIELD}",
    )
    print("WRITTEN. GET-verified on the record:")
    print(f"  {TRANSCRIPT_DOC_URL_FIELD}: {_fmt(stored.get(TRANSCRIPT_DOC_URL_FIELD))}")
    print(f"  {AI_SUMMARY_FIELD}: "
          f"{'set' if stored.get(AI_SUMMARY_FIELD) else 'empty'}")
    print(f"  nextSteps: {'set' if stored.get('nextSteps') else 'empty'}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", default=os.environ.get("FATHOM_API_KEY", ""),
                        help="Fathom API key (default: $FATHOM_API_KEY)")
    parser.add_argument("--base-url", default=os.environ.get(
        "FATHOM_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--days", type=int, default=14,
                        help="listing window in days (default 14)")
    parser.add_argument("--match", action="store_true",
                        help="also pair CRM candidate sessions (read-only)")
    parser.add_argument("--deliver", metavar="SESSION_ID",
                        help="WRITE the transcript back to this one session")
    args = parser.parse_args()
    settings = Settings()
    if not args.key:
        args.key = settings.fathom_api_key  # .env fallback
    if not args.key:
        sys.exit("No Fathom key: export FATHOM_API_KEY=..., put it in .env, "
                 "or pass --key.")
    client = FathomClient(args.key, base_url=args.base_url)
    now = datetime.now(timezone.utc)
    # --days drives the source's sweep window too, so an old test recording
    # is still matchable (the worker itself uses transcript_give_up_days).
    source = FathomTranscriptSource(client, now=now, give_up_days=args.days)

    await list_meetings(client, args.days)

    if args.match or args.deliver:
        espo = EspoClient(settings.espo_base_url, settings.espo_api_key)
        print(f"\nCRM: {settings.espo_base_url}")
        if args.match:
            await match_sessions(settings, espo, source)
        if args.deliver:
            await deliver_one(settings, espo, source, args.deliver)


if __name__ == "__main__":
    asyncio.run(main())
