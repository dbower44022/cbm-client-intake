"""Make the two Needs you examples a check cannot make by hand (the home page,
phase 3; prds/home-page-plan.md § 8, stop 3).

Two of the home page's Needs you kinds have no screen that makes them on a
training system:

* **Summary**: a Completed session with a meeting summary and empty session
  notes. The summary field is written only by the note taker, which does not
  run on a training system, and is on no screen. This adds one Completed
  session, three days ago, on ``Fernwood Landscaping — Mentoring``, with a
  meeting summary and no notes.
* **Email**: a conversation waiting for a reply. The training addresses have
  no mailboxes, so no mail ever arrives. This adds one inbound message,
  three days ago, to the ``Cash-flow forecast for the new oven`` thread on
  ``Brightline Bakehouse — Mentoring``, so the thread's last message is the
  client's.

Training systems only (``targets.resolve`` refuses any other CRM). Idempotent
by name. Read-only unless ``--apply``. The records stay until the system is
restored; on the Business Mentors Association's system that is one more
record for its owed baseline re-capture (OPEN-ITEMS #87).

    uv run python scripts/sandbox/home_needs_examples.py --env-file ~/.config/cbm-bma/bma.env
    uv run python scripts/sandbox/home_needs_examples.py --env-file ~/.config/cbm-bma/bma.env --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.espo import EspoClient, EspoError  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import targets as sandbox_targets  # noqa: E402

CRM_FMT = "%Y-%m-%d %H:%M:%S"
SUMMARY_ENGAGEMENT = "Fernwood Landscaping — Mentoring"
SUMMARY_SESSION = "Home page check — meeting summary"
SUMMARY_HTML = (
    "<p><b>Meeting summary</b> (training example): reviewed the spring "
    "booking backlog and the cost of a second crew. Agreed to price two "
    "service tiers before the next meeting.</p>"
)
EMAIL_ENGAGEMENT = "Brightline Bakehouse — Mentoring"
EMAIL_THREAD = "Cash-flow forecast for the new oven"
EMAIL_BODY = ("Thanks, Joe. I filled in the forecast. Could you look at the "
              "March numbers before we order the oven?")
DAYS_AGO = 3


async def one(client: EspoClient, entity: str, name: str, select: str = "id,name") -> dict | None:
    data = await client.list(entity, select=select, max_size=1,
                             where=[{"type": "equals", "attribute": "name", "value": name}])
    rows = data.get("list") or []
    return rows[0] if rows else None


async def summary_session(client: EspoClient, apply: bool, now: datetime) -> str:
    engagement = await one(client, "CEngagement", SUMMARY_ENGAGEMENT, "id,name,assignedUsersIds")
    if not engagement:
        return f"! no engagement {SUMMARY_ENGAGEMENT!r}: summary example skipped"
    if await one(client, "CSession", SUMMARY_SESSION):
        return f"summary example already on {SUMMARY_ENGAGEMENT}"
    if apply:
        start = (now - timedelta(days=DAYS_AGO)).replace(hour=15, minute=0, second=0, microsecond=0)
        users = engagement.get("assignedUsersIds") or []
        payload = {
            "name": SUMMARY_SESSION,
            "status": "Completed",
            "sessionType": "Client Session",
            "dateStart": start.strftime(CRM_FMT),
            "dateEnd": (start + timedelta(hours=1)).strftime(CRM_FMT),
            "engagementId": engagement["id"],
            "sessionAiSummary": SUMMARY_HTML,
        }
        if users:
            payload["assignedUserId"] = users[0]
            payload["assignedUsersIds"] = users
        await client.create("CSession", payload)
    return f"add a Completed session {SUMMARY_SESSION!r} with a meeting summary to {SUMMARY_ENGAGEMENT}"


async def inbound_email(client: EspoClient, apply: bool, now: datetime, target) -> str:
    conv = await one(client, "CConversation", EMAIL_THREAD, "id,name,messageCount")
    if not conv:
        return f"! no thread {EMAIL_THREAD!r}: email example skipped"
    last = (await client.list(
        "CCommunication", max_size=1, select="direction,snippet",
        where=[{"type": "equals", "attribute": "conversationId", "value": conv["id"]}],
        order_by="sentAt", order="desc")).get("list") or []
    if last and last[0].get("direction") == "Inbound":
        return f"thread {EMAIL_THREAD!r} already ends with the client's message"
    if apply:
        sent = (now - timedelta(days=DAYS_AGO)).replace(hour=14, minute=0, second=0, microsecond=0)
        await client.create("CCommunication", sandbox_targets.localise({
            "name": EMAIL_THREAD,
            "conversationId": conv["id"],
            "direction": "Inbound",
            "sentAt": sent.strftime(CRM_FMT),
            "fromName": "Sandbox Contact",
            "fromAddress": "contact@sandbox.cbmentors.org",
            "toAddresses": "joe.mentor@sandbox.cbmentors.org",
            "bodyCleaned": f"<p>{EMAIL_BODY}</p>",
            "snippet": EMAIL_BODY[:100],
            "sourceMailbox": "joe.mentor@sandbox.cbmentors.org",
        }, target))
        await client.update("CConversation", conv["id"], {
            "lastMessageAt": sent.strftime(CRM_FMT),
            "messageCount": int(conv.get("messageCount") or 0) + 1,
        })
    return f"add the client's reply to {EMAIL_THREAD!r} on {EMAIL_ENGAGEMENT}"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="actually write")
    sandbox_targets.add_env_file_argument(parser)
    args = parser.parse_args()

    base, api_key, timeout = sandbox_targets.api_connection(args.env_file)
    target = sandbox_targets.resolve(base)
    if target is None:
        print(sandbox_targets.refusal(base))
        return 2
    client = EspoClient(base, api_key, timeout)
    now = datetime.now(timezone.utc)
    print(f"\nNeeds you examples on {base}")
    print("APPLY\n" if args.apply else "DRY RUN — nothing will be written\n")
    try:
        for line in (await summary_session(client, args.apply, now),
                     await inbound_email(client, args.apply, now, target)):
            print(f"  {'' if args.apply or line.startswith(('!', 'summary example already', 'thread ')) else 'would '}{line}")
    except EspoError as exc:
        print(f"\nSTOPPED: {exc}")
        return 1
    if not args.apply:
        print("\nRe-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
