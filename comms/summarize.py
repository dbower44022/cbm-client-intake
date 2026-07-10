"""Optional AI layer: per-conversation summaries via the Claude API.

Gated by ``COMMS_AI_SUMMARY`` (default off) — with the flag off this module is
never invoked, no ``ANTHROPIC_API_KEY`` is needed, and no email content leaves
Google/the CRM (plan §5.6). When on, the worker runs a pass after each sync:
every conversation whose ``summarizedAt`` is null (new, or re-opened by a new
message) gets a 2–4 sentence summary, an Open/Closed/Uncertain status, action
items, and topic tags — written back onto the ``CConversation`` record.

Structured outputs via ``client.messages.parse`` (schema-validated — no
JSON-in-prompt parsing). A failed call degrades the conversation to
``Uncertain`` and stamps ``summarizedAt`` so one bad thread can't wedge the
pass; the next inbound message re-opens it for another attempt.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel

from core.espo import EspoError

from .crm import COMMUNICATION, CONVERSATION, CONVERSATION_FK

log = logging.getLogger("cbm_intake.comms.summarize")

_BATCH = 20            # conversations per pass
_MAX_CHARS = 6000      # transcript cap sent to the model
_HEAD, _TAIL = 2, 3    # long threads: first 2 + last 3 messages

_SYSTEM = """You are an analyst for Cleveland Business Mentors (CBM), a nonprofit
whose mentors advise small-business clients. You are given one email
conversation between a CBM manager and their client/partner/sponsor contacts.

Summarize it for the manager's record view:
- status: "Open" if anything appears unresolved or awaiting a reply, "Closed"
  only when the thread clearly concluded, "Uncertain" if you cannot tell.
  When in doubt, prefer "Open".
- summary: 2-4 plain sentences. What the conversation is about and where it
  stands. No preamble.
- action_items: concrete next steps mentioned or clearly implied (empty list
  if none). Each a short imperative phrase.
- key_topics: 1-4 short tags (e.g. "financing", "hiring", "session scheduling")."""


class ConversationSummary(BaseModel):
    status: Literal["Open", "Closed", "Uncertain"]
    summary: str
    action_items: list[str]
    key_topics: list[str]


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _transcript(messages: list[dict[str, Any]]) -> str:
    """A compact plain-text transcript (oldest first, head+tail on long threads)."""
    msgs = sorted(messages, key=lambda m: m.get("sentAt") or "")
    if len(msgs) > _HEAD + _TAIL:
        kept = msgs[:_HEAD] + [{"_gap": len(msgs) - _HEAD - _TAIL}] + msgs[-_TAIL:]
    else:
        kept = msgs
    lines: list[str] = []
    for m in kept:
        if "_gap" in m:
            lines.append(f"[... {m['_gap']} earlier messages omitted ...]")
            continue
        who = m.get("fromName") or m.get("fromAddress") or "?"
        body = _strip_html(m.get("bodyCleaned") or m.get("snippet") or "")
        lines.append(f"--- {m.get('sentAt') or ''} | {who} ({m.get('direction')}) ---\n{body}")
    text = "\n\n".join(lines)
    return text[:_MAX_CHARS]


def _strip_html(html: str) -> str:
    import re

    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"</p\s*>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    import html as html_mod

    return html_mod.unescape(text).strip()


async def summarize_conversation(
    anthropic_client: Any, model: str, messages: list[dict[str, Any]]
) -> ConversationSummary:
    response = await anthropic_client.messages.parse(
        model=model,
        max_tokens=1024,
        system=_SYSTEM,
        messages=[{"role": "user", "content": _transcript(messages)}],
        output_format=ConversationSummary,
    )
    return response.parsed_output


async def run_summary_pass(settings: Any, espo: Any) -> int:
    """Summarize every conversation with ``summarizedAt`` null. Returns count."""
    if not (settings.comms_ai_summary and settings.anthropic_api_key):
        return 0
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    data = await espo.list(
        CONVERSATION,
        where=[{"type": "isNull", "attribute": "summarizedAt"}],
        select="name,messageCount",
        max_size=_BATCH,
        order_by="lastMessageAt",
        order="desc",
    )
    done = 0
    for conv in data.get("list", []):
        if not int(conv.get("messageCount") or 0):
            continue
        try:
            msgs = await espo.list(
                COMMUNICATION,
                where=[{"type": "equals", "attribute": CONVERSATION_FK, "value": conv["id"]}],
                select="sentAt,direction,fromName,fromAddress,snippet,bodyCleaned",
                max_size=50,
                order_by="sentAt",
            )
            result = await summarize_conversation(
                client, settings.summary_model, msgs.get("list", [])
            )
            await espo.update(
                CONVERSATION,
                conv["id"],
                {
                    "conversationStatus": result.status,
                    "summary": result.summary,
                    "actionItems": "\n".join(result.action_items),
                    "keyTopics": ", ".join(result.key_topics)[:250],
                    "summarizedAt": _now_stamp(),
                },
            )
            done += 1
        except EspoError as exc:
            log.warning("summary CRM write failed for %s: %s", conv["id"], exc)
        except Exception as exc:  # noqa: BLE001 — API/parse failure: degrade, don't wedge
            log.warning("summary failed for %s (%s): %s", conv["id"], conv.get("name"), exc)
            try:
                await espo.update(
                    CONVERSATION,
                    conv["id"],
                    {"conversationStatus": "Uncertain", "summarizedAt": _now_stamp()},
                )
            except EspoError:
                pass
    if done:
        log.info("summarized %d conversations", done)
    return done
