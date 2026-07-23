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

**Deletion** (added 2026-07-22 — the prod report found 373 internal-only
conversations / 798 messages, far beyond UI deletion): ``--delete`` removes
each internal-only conversation's CCommunications and then the CConversation
itself, authenticated as the ADMIN provisioning service account
(``ESPO_PROVISION_USERNAME`` / ``ESPO_PROVISION_PASSWORD`` — present in the
deployed containers' env; the intake API key has no delete grant by design).
``--delete-shells`` additionally removes EMPTY conversation shells older
than ``--shell-age-days`` (default 2 — a very recent shell may be a send
mid-flight). Both print exactly what they deleted; failures are per-record
and never abort the run.

    .venv/bin/python scripts/list_internal_conversations.py --delete
    .venv/bin/python scripts/list_internal_conversations.py --delete --delete-shells
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


async def _admin_client(settings) -> EspoClient:
    """An EspoClient authenticated as the provisioning ADMIN account (the
    only identity with delete rights; the intake API key is create-only)."""
    from assignments.auth import login_token

    username = settings.espo_provision_username
    password = settings.espo_provision_password
    if not username or not password:
        raise SystemExit(
            "--delete needs ESPO_PROVISION_USERNAME / ESPO_PROVISION_PASSWORD "
            "in the env (present in the deployed worker/web containers)."
        )
    user_name, token = await login_token(
        settings.espo_base_url, username, password, settings.request_timeout_seconds
    )
    return EspoClient.for_user_token(
        settings.espo_base_url, user_name, token, settings.request_timeout_seconds
    )


async def run(
    domains: set[str],
    delete: bool = False,
    delete_shells: bool = False,
    shell_age_days: int = 2,
) -> int:
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

    if not delete:
        if internal or shells:
            print("\nRe-run with --delete (and optionally --delete-shells) to remove.")
        return 0

    # --- deletion (as the admin service account) ------------------------------
    from datetime import datetime, timedelta, timezone

    admin = await _admin_client(settings)
    deleted_convs = deleted_msgs = failed = 0
    for conv, msgs, _addrs in internal:
        ok = True
        for m in msgs:
            try:
                await admin.delete(COMMUNICATION, m["id"])
                deleted_msgs += 1
            except EspoError as exc:
                failed += 1
                ok = False
                print(f"  DELETE FAILED (message {m['id']}): {exc}")
        if ok:
            try:
                await admin.delete(CONVERSATION, conv["id"])
                deleted_convs += 1
            except EspoError as exc:
                failed += 1
                print(f"  DELETE FAILED (conversation {conv['id']}): {exc}")
    shell_cutoff = datetime.now(timezone.utc) - timedelta(days=shell_age_days)
    deleted_shells = 0
    if delete_shells:
        for conv in shells:
            created = str(conv.get("createdAt") or "")
            try:
                created_dt = datetime.strptime(created, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                continue  # unparseable stamp — leave it for the UI
            if created_dt > shell_cutoff:
                continue  # too recent — could be a send mid-flight
            try:
                await admin.delete(CONVERSATION, conv["id"])
                deleted_shells += 1
            except EspoError as exc:
                failed += 1
                print(f"  DELETE FAILED (shell {conv['id']}): {exc}")
    print(
        f"\nDeleted {deleted_convs} internal conversations, {deleted_msgs} messages"
        + (f", {deleted_shells} empty shells" if delete_shells else "")
        + (f"; {failed} failures." if failed else "; no failures.")
    )
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--domains",
        default="",
        help="comma-separated internal domains (default: COMMS_INTERNAL_DOMAINS)",
    )
    ap.add_argument(
        "--delete", action="store_true",
        help="delete internal-only conversations + their messages (admin creds)",
    )
    ap.add_argument(
        "--delete-shells", action="store_true",
        help="with --delete: also remove empty shells older than --shell-age-days",
    )
    ap.add_argument("--shell-age-days", type=int, default=2)
    args = ap.parse_args()
    settings = get_settings()
    domains = {
        d.strip().lower().lstrip("@")
        for d in (args.domains or settings.comms_internal_domains).split(",")
        if d.strip()
    }
    raise SystemExit(asyncio.run(run(
        domains,
        delete=args.delete,
        delete_shells=args.delete_shells,
        shell_age_days=args.shell_age_days,
    )))


if __name__ == "__main__":
    main()
