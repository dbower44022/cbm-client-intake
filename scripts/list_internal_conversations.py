"""List INTERNAL-ONLY conversations in the CRM, for manual cleanup.

Since v0.127.0 the Gmail sweep no longer ingests staff-to-staff mail
(``COMMS_INTERNAL_DOMAINS``), but conversations stored before the fix remain
in the CRM and the intake API user cannot delete records — cleanup happens in
the EspoCRM UI. This script is READ-ONLY: it walks every ``CCommunication``,
groups messages by conversation, and reports each conversation whose every
participant address (From/To/Cc across all its messages) is at an internal
domain — plus, separately, empty conversation shells with no messages at all.

Output per conversation: subject, message count, date range, the participant
addresses, and a direct CRM link. Delete in the EspoCRM UI: open the link,
remove the conversation's CCommunication records (they are NOT cascade-deleted
with the conversation), then the CConversation itself — or mass-select in the
CConversation / CCommunication list views searching by the printed names.

Usage (reads ESPO_BASE_URL / ESPO_API_KEY from the env / .env — crm-test by
default; for prod use the overlay-key one-liner from CLAUDE.md's "Form
dropdown lists" section, or run in the deployed worker console):

    uv run python scripts/list_internal_conversations.py
    uv run python scripts/list_internal_conversations.py --domains cbmentors.org
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_settings  # noqa: E402
from core.espo import EspoClient, EspoError  # noqa: E402

CONVERSATION = "CConversation"
COMMUNICATION = "CCommunication"
PAGE = 200
MSG_SELECT = "id,conversationId,fromAddress,toAddresses,ccAddresses,sentAt"
CONV_SELECT = "id,name,lastMessageAt,createdAt"


def _addresses(msg: dict) -> set[str]:
    out: set[str] = set()
    frm = (msg.get("fromAddress") or "").strip().lower()
    if frm:
        out.add(frm)
    for field in ("toAddresses", "ccAddresses"):
        for part in (msg.get(field) or "").split(","):
            addr = part.strip().lower()
            if addr:
                out.add(addr)
    return out


def _is_internal(addr: str, domains: set[str]) -> bool:
    return addr.rsplit("@", 1)[-1] in domains


async def _list_all(client: EspoClient, entity: str, select: str) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        page = await client.list(entity, select=select, max_size=PAGE, offset=offset)
        batch = page.get("list", [])
        rows.extend(batch)
        offset += PAGE
        if len(batch) < PAGE:
            break
    return rows


async def run(domains: set[str]) -> int:
    settings = get_settings()
    if not settings.espo_base_url or not settings.espo_api_key:
        print("ESPO_BASE_URL / ESPO_API_KEY must be set (see the module docstring).")
        return 2
    base = settings.espo_base_url.rstrip("/")
    client = EspoClient(settings.espo_base_url, settings.espo_api_key)

    try:
        messages = await _list_all(client, COMMUNICATION, MSG_SELECT)
        conversations = await _list_all(client, CONVERSATION, CONV_SELECT)
    except EspoError as exc:
        print(f"CRM read failed: {exc}")
        return 2

    by_conv: dict[str, list[dict]] = defaultdict(list)
    for m in messages:
        cid = m.get("conversationId") or ""
        if cid:
            by_conv[cid].append(m)

    internal: list[tuple[dict, list[dict], set[str]]] = []
    shells: list[dict] = []
    for conv in conversations:
        msgs = by_conv.get(conv["id"], [])
        if not msgs:
            shells.append(conv)
            continue
        addrs: set[str] = set()
        for m in msgs:
            addrs |= _addresses(m)
        if addrs and all(_is_internal(a, domains) for a in addrs):
            internal.append((conv, msgs, addrs))

    print(
        f"{len(conversations)} conversations / {len(messages)} messages in the CRM; "
        f"internal domains: {', '.join(sorted(domains))}\n"
    )

    if not internal:
        print("No internal-only conversations found.")
    else:
        total_msgs = sum(len(m) for _, m, _ in internal)
        print(
            f"=== {len(internal)} INTERNAL-ONLY conversations "
            f"({total_msgs} messages) — cleanup candidates ===\n"
        )
        internal.sort(key=lambda t: t[0].get("lastMessageAt") or "", reverse=True)
        for conv, msgs, addrs in internal:
            dates = sorted(m.get("sentAt") or "" for m in msgs)
            span = dates[0][:10] if dates[0] else "?"
            if len(dates) > 1 and dates[-1][:10] != span:
                span += f" → {dates[-1][:10]}"
            print(f"- {conv.get('name') or '(no subject)'}")
            print(f"    {len(msgs)} message(s), {span}; {', '.join(sorted(addrs))}")
            print(f"    {base}/#{CONVERSATION}/view/{conv['id']}")

    if shells:
        print(f"\n=== {len(shells)} conversations with NO messages (empty shells) ===")
        for conv in shells:
            print(
                f"- {conv.get('name') or '(no subject)'} "
                f"(created {str(conv.get('createdAt') or '?')[:10]}) — "
                f"{base}/#{CONVERSATION}/view/{conv['id']}"
            )
        print(
            "Shells are usually failed first-message ingests; verify in the UI "
            "before deleting (a very recent one may be a send mid-flight)."
        )
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--domains",
        default="",
        help="comma-separated internal domains (default: COMMS_INTERNAL_DOMAINS)",
    )
    args = ap.parse_args()
    settings = get_settings()
    domains = {
        d.strip().lower().lstrip("@")
        for d in (args.domains or settings.comms_internal_domains).split(",")
        if d.strip()
    }
    raise SystemExit(asyncio.run(run(domains)))


if __name__ == "__main__":
    main()
