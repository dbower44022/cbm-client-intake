"""Email Template integration (ET) — EspoCRM renders, the app sends.

The compose dialogs offer the EspoCRM email templates the signed-in user may
see; selecting one loads a fully rendered draft. Rendering is EspoCRM's own
parse action — this app NEVER substitutes placeholders (Decision ET-D1 /
ET-112 of ``prompts/email templates/…/CRMBuilder-PRD-EmailTemplateIntegration.docx``).

Integration facts, verified live against crm-test (EspoCRM 9.3.6, 2026-07-16,
closing PRD open issues ET-OI-1 and ET-OI-4):

- **List**: ``GET EmailTemplate`` (orderBy name, optional ``contains`` filter)
  under the acting user's token — role/team visibility is EspoCRM's (ET-101).
  The scope defaults to no access: a role without an ``EmailTemplate`` grant
  sees an empty picker (Mentor Role: read=team; Standard User: read=all;
  Partner/Sponsor Manager roles need the grant added — CRM handoff).
- **Render**: ``POST EmailTemplate/{id}/prepare`` with any of
  ``{parentType, parentId, emailAddress}``. Response:
  ``{subject, body, isHtml, attachmentsIds, attachmentsNames}``.
  ``parentType``/``parentId`` feeds ``{Parent.*}``; ``emailAddress``
  independently resolves ``{Person.*}`` by looking the address up across
  Contact/Lead/Account/User (so a record-less quick-compose still
  personalizes — ET-OI-1). Both may be passed together. ACL applies
  server-side to the template AND each referenced record.
- **Unresolved placeholders stay literal** (``{Person.name}``), they do not
  render as blanks — ``leftover_tokens`` reports them so the UI can warn
  (the ET-OI-2 notice) while never blocking (ET-B2).
- **Attachments are cloned per parse**: the returned ids are fresh Attachment
  copies owned by the acting user. Bytes are NOT downloaded here — chips only
  (ET-B3); the send path downloads at send time and a failure blocks the send
  (ET-131). Unsent clones are EspoCRM-garbage-collected.
- **Context filter rides the NATIVE category** (``EmailTemplate.category`` →
  ``EmailTemplateCategory``, a CategoryTree — EmailTemplate itself has
  ``customizable: false``, so it never appears in Entity Manager and can't
  take a custom field through the UI; found 2026-07-16 when the original
  cAppliesTo plan hit that wall). A template whose category is named
  ``Engagement``/``Partner``/``Sponsor`` (case-insensitive) shows only in
  that domain's compose; any other category — or none — shows everywhere.
  Zero CRM build: admins just create/assign those categories when they want
  the filtering.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

log = logging.getLogger("cbm_intake.comms.templates")

# Compose context per session-tool parent entity — also the recognized
# EmailTemplateCategory names (case-insensitive) that scope a template to one
# domain. Quick-compose has no record context and passes context=None.
CONTEXT_BY_PARENT = {
    "CEngagement": "Engagement",
    "CPartnerProfile": "Partner",
    "CSponsorProfile": "Sponsor",
}
_CONTEXT_CATEGORIES = {v.lower() for v in CONTEXT_BY_PARENT.values()}

# {Person.firstName}-style tokens that survived the render — entity-qualified
# only, so ordinary braces in prose don't false-positive.
_TOKEN = re.compile(r"\{[A-Z][A-Za-z0-9]*\.[A-Za-z0-9_]+\}")

_SCRIPT_BLOCK = re.compile(r"<\s*(script|style)\b.*?<\s*/\s*\1\s*>", re.IGNORECASE | re.DOTALL)
_EVENT_ATTR = re.compile(r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE)
_JS_URL = re.compile(r"(\shref|\ssrc)\s*=\s*([\"']?)\s*javascript:[^\"'>\s]*\2", re.IGNORECASE)


def sanitize_template_html(html: str) -> str:
    """Light safety pass over CRM-authored template HTML before it enters the
    editor: drop script/style blocks, inline event handlers, javascript: URLs.
    Formatting (tags, inline styles) is kept — templates are trusted staff
    content, this is defense in depth; the editor sanitizes again on load."""
    html = _SCRIPT_BLOCK.sub("", html or "")
    html = _EVENT_ATTR.sub("", html)
    html = _JS_URL.sub(r"\1=\2\2", html)
    return html


def leftover_tokens(subject: str, body: str) -> list[str]:
    """Placeholder tokens EspoCRM could not resolve (missing person/record).
    Order-preserving, deduped."""
    seen: dict[str, None] = {}
    for token in _TOKEN.findall(subject or "") + _TOKEN.findall(body or ""):
        seen.setdefault(token)
    return list(seen)


async def list_templates(
    user_client: Any, q: str = "", context: Optional[str] = None
) -> dict[str, Any]:
    """Templates visible to the acting user, name-ordered, optionally
    type-ahead-filtered (``q``) and context-filtered by the native category.

    A template only leaves the list when BOTH sides are explicit: a context
    was given AND the template's category name is one of the recognized
    domain names but not this one. Everything else — no category, an
    organizational category ("Newsletters"), an unreadable name — shows
    everywhere, so the filter can never hide a template by accident."""
    select = "id,name" + (",categoryId,categoryName" if context else "")
    where = None
    if q:
        where = [{"type": "contains", "attribute": "name", "value": q}]
    data = await user_client.list(
        "EmailTemplate", select=select, where=where,
        order_by="name", order="asc", max_size=100,
    )
    rows = data.get("list", []) or []
    templates = []
    for row in rows:
        if context:
            cat = str(row.get("categoryName") or "").strip().lower()
            if cat in _CONTEXT_CATEGORIES and cat != context.lower():
                continue
        templates.append({"id": row.get("id"), "name": row.get("name")})
    return {"templates": templates, "contextFiltered": bool(context)}


async def parse_template(
    user_client: Any,
    template_id: str,
    *,
    parent_type: Optional[str] = None,
    parent_id: Optional[str] = None,
    email_address: Optional[str] = None,
) -> dict[str, Any]:
    """Render a template server-side into an editable draft payload.

    Returns ``subject``, sanitized ``bodyHtml``, ``attachments`` as
    ``[{id, name}]`` chips (ids only — bytes stay in the CRM until send,
    ET-B3), and ``leftoverTokens`` for the unresolved-placeholder notice.
    EspoErrors propagate — the routers map them (403 = no template access,
    ET-114's non-destructive error)."""
    out = await user_client.email_template_prepare(
        template_id,
        parent_type=parent_type,
        parent_id=parent_id,
        email_address=email_address,
    )
    subject = out.get("subject") or ""
    body = out.get("body") or ""
    if not out.get("isHtml", True):
        from core.email_clean import _text_to_html

        body = _text_to_html(body)
    body = sanitize_template_html(body)
    names = out.get("attachmentsNames") or {}
    attachments = [
        {"id": aid, "name": names.get(aid) or "attachment"}
        for aid in out.get("attachmentsIds") or []
    ]
    return {
        "subject": subject,
        "bodyHtml": body,
        "attachments": attachments,
        "leftoverTokens": leftover_tokens(subject, body),
    }
