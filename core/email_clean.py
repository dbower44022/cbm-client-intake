"""Email cleaning: strip quoted replies, signatures, and boilerplate.

Ported from the CRM_Extender project's production-validated pipeline
(``poc/email_parser.py`` + ``poc/html_email_parser.py`` — validated on a
3,752-email production corpus; see prds/communications-gmail-integration.md
§5.5 and the upstream ``PRDs/email-stripping.md`` for the design rationale
and edge-case tuning). Two tracks:

- **HTML-first** (when an HTML body exists): ``quotequail`` splits the reply
  from the quoted history, BeautifulSoup removes signature/quote/footer
  containers by CSS selector (with the "whole body inside gmail_signature"
  resilience re-parse), then the shared text-level cleanup runs.
- **Plain-text fallback**: ``mail-parser-reply`` plus a regex layer for
  forwarded headers, "On … wrote:", mobile signatures, legal disclaimers,
  ``--``/``____`` signature separators (with the tuned false-positive
  guards), promotional blocks, and hard-wrap unwrapping.

Output (:class:`CleanedEmail`): **the author's new content only** — quoted
reply chains, signatures, and boilerplate are all removed (Doug, 2026-07-11:
each stored message must be just the new text; the full original stays one
click away in Gmail). The extracted quoted chain is still returned on the
dataclass (``quoted``) for callers that want it, but it is NOT part of the
stored/rendered HTML.

Deliberate v1 simplification: the stored HTML is regenerated from the cleaned
TEXT (paragraphs + line breaks), not the original markup — cleaning quality
exactly matches the proven text pipeline, and the sender's original formatting
stays reachable via the message's "Open in Gmail" link.
"""

from __future__ import annotations

import html as html_mod
import logging
import re
from dataclasses import dataclass

log = logging.getLogger("cbm_intake.email_clean")

# --- plain-text patterns (ported verbatim unless noted) ----------------------

_FORWARDED_HEADER = re.compile(
    r"^-{2,}\s*Forwarded message\s*-{2,}\s*$", re.MULTILINE | re.IGNORECASE
)

_MOBILE_SIGNATURE = re.compile(
    r"^(Sent from my (iPhone|iPad|Galaxy|Android|Pixel|BlackBerry)|"
    r"Get Outlook for (iOS|Android)|"
    r"Sent from Yahoo Mail|"
    r"Sent from Mail for Windows|"
    r"This email was sent from a notification[\-\s]*(?:only\s+)?(?:email\s+)?address)\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# "On <date> <someone> wrote:" — tolerates the header wrapping onto a second
# line (Gmail plain-text quoting wraps at ~78 chars; seen in live mail).
_ON_WROTE = re.compile(
    r"^On\s+[^\n]{10,150}(?:\n[^\n]{0,100})?wrote:\s*$", re.MULTILINE
)

_OUTLOOK_SEPARATOR = re.compile(
    r"^_{10,}\s*$|^-{10,}\s*$|^From:\s+.+\nSent:\s+.+\nTo:\s+.+", re.MULTILINE
)

_CONFIDENTIAL_NOTICE = re.compile(
    r"^.*("
    r"confidential(?:ity)?\s*(?:notice|and\s+privileged)|"
    r"intended\s+(?:only\s+)?for\s+(?:the\s+)?(?:use\s+of\s+)?(?:the\s+)?(?:individual|person|recipient|addressee)|"
    r"if\s+you\s+(?:are\s+)?not\s+(?:the\s+)?intended\s+(?:recipient|addressee)|"
    r"(?:notify|contact)\s+(?:the\s+)?sender\s+immediately|"
    r"delete\s+(?:this\s+)?(?:email|message|e-mail)|"
    r"(?:disclosure|copying|distribution|dissemination)\s+(?:is\s+)?(?:strictly\s+)?prohibited|"
    r"unauthorized\s+(?:use|access|disclosure|review|distribution)|"
    r"may\s+contain\s+(?:confidential|privileged|proprietary)\s+information|"
    r"this\s+e?-?mail\s+.*(?:is\s+|are\s+)?confidential"
    r").*$",
    re.MULTILINE | re.IGNORECASE,
)

_ENVIRONMENTAL_MESSAGE = re.compile(
    r"^.*(?:"
    r"please\s+(?:consider|think)\s+(?:about\s+)?(?:the\s+)?environment\s+before\s+printing|"
    r"think\s+before\s+(?:you\s+)?print|"
    r"save\s+(?:a\s+)?tree|"
    r"go\s+green|"
    r"don['']?t\s+print\s+(?:this\s+email)?"
    r").*$",
    re.MULTILINE | re.IGNORECASE,
)

_VALEDICTION = re.compile(
    r"^[\s]*(?:"
    r"(?:Best\s+)?Regards?|"
    r"Sincerely|"
    r"(?:Many\s+)?Thanks|"
    r"Thank\s+you|"
    r"Cheers|"
    r"Yours\s+(?:truly|sincerely|faithfully)|"
    r"Kind\s+regards?|"
    r"Warm\s+regards?|"
    r"Best\s+wishes?|"
    r"All\s+the\s+best|"
    r"Take\s+care|"
    r"Respectfully|"
    r"Best"
    r"),?[\s]*$",
    re.MULTILINE | re.IGNORECASE,
)

# Signature-content markers. Retuned from the upstream (financial-advisory)
# vocabulary to a generic small-business set — phone/email/URL/org/title
# markers kept; the long credential list trimmed to common ones.
_SIGNATURE_CONTENT = re.compile(
    r"(?:"
    r"(?:Tel|Phone|Fax|Mobile|Cell|Direct|Office)\s*[:\.]?\s*[\+\d\(\)\-\s]{7,}|"
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|"
    r"(?:www\.|https?://)|"
    r"(?:Dept\.|Department|University|Corp\.|Corporation|Inc\.|LLC|Ltd\.)|"
    r"(?:Professor|Director|Manager|CEO|CTO|CFO|COO|VP|Vice\s+President|President|Founder|"
    r"Owner|Engineer|Analyst|Partner|Associate|Advisor|Mentor|Consultant|Specialist|"
    r"Coordinator|Administrator|Assistant)|"
    r"(?:CPA|MBA|JD|PhD|MD|Esq|PMP)®?"
    r")",
    re.IGNORECASE,
)

_EMBEDDED_IMAGE = re.compile(r"\[cid:[^\]]+\]", re.IGNORECASE)

_SOCIAL_LINKS = re.compile(
    r"^.*(?:"
    r"LinkedIn\s*<|Twitter\s*<|Facebook\s*<|Instagram\s*<|"
    r"Follow\s+(?:us|me)\s+(?:on|at)|"
    r"Connect\s+(?:with\s+(?:us|me)|on\s+LinkedIn)"
    r").*$",
    re.MULTILINE | re.IGNORECASE,
)

_VCARD_PATTERN = re.compile(
    r"^.*(?:"
    r"Download\s+(?:my\s+)?VCard|"
    r"(?:Click\s+Here|request\s+a\s+link)\s*<.*>?\s*to\s+send\s+files\s+securely|"
    r"To\s+request\s+a\s+link\s+to\s+send\s+files\s+securely"
    r").*$",
    re.MULTILINE | re.IGNORECASE,
)

_CREDS = r"(?:CPA|MBA|JD|PhD|MD|Esq|PMP)®?"

_NAME_LINE = re.compile(
    r"^[\s]*([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+){1,3})"
    rf"(?:,?\s*{_CREDS}\s*)*"
    r"[\s]*$",
    re.MULTILINE,
)

_CAPS_NAME_LINE = re.compile(
    r"^[\s]*[A-Z]{2,}(?:\s+[A-Z]\.?)?(?:\s+[A-Z]{2,}){1,3}"
    rf"(?:,?\s*{_CREDS}\s*)*"
    r"[\s]*$",
    re.MULTILINE,
)


def _unwrap_lines(body: str) -> str:
    """Rejoin hard-wrapped lines while preserving intentional breaks."""
    if not body:
        return body
    lines = body.split("\n")
    result: list[str] = []
    current: list[str] = []
    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            if current:
                result.append(" ".join(current))
                current = []
            result.append("")
            continue
        is_special = (
            stripped.startswith(("-", "*", "•", ">", "|"))
            or re.match(r"^\d+[\.\)]\s", stripped)
            or stripped.startswith("--")
            or re.match(r"^[A-Z][a-z]*:\s", stripped)
        )
        starts_new = False
        if current:
            prev = current[-1]
            starts_new = bool(prev) and prev[-1] in ".!?" and stripped[0].isupper()
        if (is_special or starts_new) and current:
            result.append(" ".join(current))
            current = []
        if is_special:
            result.append(stripped)
        else:
            current.append(stripped)
    if current:
        result.append(" ".join(current))
    return "\n".join(result)


def _strip_signature_block(body: str) -> str:
    """Remove a signature block that follows a valediction — guarded so a real
    follow-up paragraph after "Regards," is never truncated."""
    m = _VALEDICTION.search(body)
    if not m:
        return body
    after = body[m.end():].strip()
    if not after:
        return body[: m.start()].rstrip()
    check = after[:1000]
    lines_after = after.split("\n")[:15]
    has_markers = _SIGNATURE_CONTENT.search(check)
    is_short = len(after) < 1500 or len(lines_after) <= 15
    sentence_re = re.compile(r"^[A-Z][a-z]+(?:[ \t]+\w+){3,}[^\n]*[.!?]\s*$", re.MULTILINE)
    sig_sentence_re = re.compile(
        r"consult\s+(?:your|a)\s+(?:CPA|attorney|advisor|tax)|"
        r"(?:click|book)\s+(?:here|time)\s+(?:to|with)|"
        r"please\s+let\s+me\s+know\s+if\s+you\s+have|"
        r"thank\s+you\s+(?:for|and)|"
        r"as\s+discussed|"
        r"looking\s+forward\s+to",
        re.IGNORECASE,
    )
    has_sentences = any(
        not sig_sentence_re.search(sm.group(0)) for sm in sentence_re.finditer(check)
    )
    if has_markers and is_short and not has_sentences:
        return body[: m.start()].rstrip()
    return body


def _strip_dash_dash_signature(body: str) -> str:
    """``--`` separator — conservative (short + signature-looking) so markdown
    section dividers survive (tuned to zero false positives upstream)."""
    m = re.search(r"^--\s*$", body, re.MULTILINE)
    if not m:
        return body
    after = body[m.end():].strip()
    if not after:
        return body[: m.start()].rstrip()
    lines_after = after.split("\n")
    if not (len(after) < 500 and len(lines_after) <= 10):
        return body
    first = lines_after[0].strip()
    if _SIGNATURE_CONTENT.search(after) or _NAME_LINE.match(first) or _CAPS_NAME_LINE.match(first):
        return body[: m.start()].rstrip()
    return body


def _strip_underscore_signature(body: str) -> str:
    """Short ``____`` separator (2–9; the 10+ case is the Outlook separator)."""
    m = re.search(r"^_{2,9}\s*$", body, re.MULTILINE)
    if not m:
        return body
    after = body[m.end():].strip()
    if not after:
        return body[: m.start()].rstrip()
    lines_after = after.split("\n")
    if not (len(after) < 1500 and len(lines_after) <= 25):
        return body
    first = lines_after[0].strip()
    if _SIGNATURE_CONTENT.search(after) or _NAME_LINE.match(first) or _CAPS_NAME_LINE.match(first):
        return body[: m.start()].rstrip()
    return body


def _strip_standalone_signature(body: str) -> str:
    """Signatures without a valediction: name line + title/contact, [cid:…]."""
    lines = body.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if _EMBEDDED_IMAGE.search(stripped):
            sig_start = i
            for j in range(max(0, i - 3), i):
                prev = lines[j].strip()
                if prev and (_NAME_LINE.match(prev) or _CAPS_NAME_LINE.match(prev)):
                    sig_start = j
                    break
            return "\n".join(lines[:sig_start]).rstrip()
        if _CAPS_NAME_LINE.match(stripped):
            if _SIGNATURE_CONTENT.search("\n".join(lines[i : i + 5])):
                return "\n".join(lines[:i]).rstrip()
        if _NAME_LINE.match(stripped) and i < len(lines) - 1:
            nxt = "\n".join(lines[i : i + 4])
            has_title = bool(
                re.search(
                    r"(?:Managing\s+)?Director|Partner|President|Vice\s+President|"
                    r"Chief|Officer|Manager|Founder|Owner|Associate|Advisor|Mentor|"
                    r"Consultant|Administrator",
                    nxt,
                    re.IGNORECASE,
                )
            )
            if has_title or _SIGNATURE_CONTENT.search(nxt):
                before = "\n".join(lines[:i]).strip()
                if before and len(before) > 20:
                    return before
    return body


def _strip_unsubscribe_footer(body: str) -> str:
    m = re.search(r"^.*unsubscribe.*$", body, re.MULTILINE | re.IGNORECASE)
    if m:
        body = body[: m.start()].rstrip()
    return body


def _strip_promotional_content(body: str) -> str:
    for pattern in (_SOCIAL_LINKS, _VCARD_PATTERN):
        m = pattern.search(body)
        if m:
            body = body[: m.start()].rstrip()
    return _EMBEDDED_IMAGE.sub("", body).rstrip()


_GT_QUOTED_BLOCK = re.compile(r"^\s*>", re.MULTILINE)


def _strip_gt_quotes(text: str) -> str:
    """Truncate at the first run of ``>``-prefixed lines (plain-text quoting).

    Catches quoting that lives INSIDE an HTML body as literal text (drafts,
    some clients), where the structural HTML selectors find nothing.
    """
    m = _GT_QUOTED_BLOCK.search(text)
    if m:
        text = text[: m.start()].rstrip()
    return text


def _text_level_cleanup(text: str, outbound: bool = False) -> str:
    """The shared tail of both tracks (quote headers → mobile sigs →
    disclaimers → separators → signature detection → promo → unsubscribe →
    unwrap → whitespace).

    ``outbound=True`` = a message OUR user wrote (app compose or their own
    Gmail): only quoted reply history is removed — the signature/valediction/
    promo heuristics are for inbound mail and truncate real authored content
    (an early "Thanks," or a "Jane Smith / Consultant" introduction deleted
    everything after it — the 2026-07-21 "sent emails look cut off" report).
    """
    m = _ON_WROTE.search(text)
    if m:
        text = text[: m.start()].rstrip()
    text = _strip_gt_quotes(text)
    if outbound:
        text = _unwrap_lines(text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()
    text = _MOBILE_SIGNATURE.sub("", text).rstrip()
    m = _CONFIDENTIAL_NOTICE.search(text)
    if m:
        text = text[: m.start()].rstrip()
    m = _ENVIRONMENTAL_MESSAGE.search(text)
    if m:
        text = text[: m.start()].rstrip()
    text = _strip_dash_dash_signature(text)
    text = _strip_underscore_signature(text)
    text = _strip_dash_dash_signature(text)  # clean up a trailing --
    text = _strip_signature_block(text)
    text = _strip_standalone_signature(text)
    text = _strip_promotional_content(text)
    text = _strip_unsubscribe_footer(text)
    text = _unwrap_lines(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# --- HTML track ---------------------------------------------------------------

_QUOTE_SELECTORS = [
    "div.gmail_quote",
    "div.gmail_quote_container",
    "div.gmail_extra",
    "blockquote.gmail_quote",
    "div.yahoo_quoted",
    "blockquote[type=cite]",
]
_SIGNATURE_SELECTORS = [
    "div.gmail_signature",
    "[data-smartmail=gmail_signature]",
    "div#Signature",
]
_CUTOFF_SELECTORS = ["div#appendonsend", "div#divRplyFwdMsg"]
_OUTLOOK_BORDER_RE = re.compile(r"border-top\s*:\s*solid\s+#E1E1E1", re.IGNORECASE)


def _remove_unsubscribe_footers_html(soup) -> None:
    from bs4 import Tag

    for tag in soup.find_all(id=re.compile(r"^footerUnsubscribe", re.IGNORECASE)):
        if isinstance(tag, Tag):
            for sibling in list(tag.find_next_siblings()):
                sibling.decompose()
            tag.decompose()
    for tag in soup.find_all(string=re.compile(r"unsubscribe", re.IGNORECASE)):
        parent = tag.parent
        if parent is not None and isinstance(parent, Tag):
            container = parent
            for _ in range(5):
                if container.name in ("div", "td", "p", "tr", "table", "body"):
                    break
                if container.parent is not None and isinstance(container.parent, Tag):
                    container = container.parent
                else:
                    break
            if container.name != "body":
                for sibling in list(container.find_next_siblings()):
                    sibling.decompose()
                container.decompose()
                break


def _remove_outlook_separators_html(soup) -> None:
    from bs4 import Tag

    for tag in soup.find_all(style=True):
        if isinstance(tag, Tag) and _OUTLOOK_BORDER_RE.search(tag.get("style", "")):
            for sibling in list(tag.find_next_siblings()):
                sibling.decompose()
            tag.decompose()
            break


def _html_track(html: str, outbound: bool = False) -> tuple[str, str]:
    """(author_text, quoted_text) from an HTML body — structural stripping.

    ``quoted_text`` is the meaningful quoted reply chain (kept for the
    de-emphasized zone); signatures/boilerplate are removed outright.
    ``outbound=True`` keeps the author's signature and footers — only the
    quoted history (quote containers / cutoff markers) is removed.
    """
    from bs4 import BeautifulSoup

    quoted_chunks: list[str] = []

    # 1. quotequail: split reply vs quoted; keep the first reply block.
    try:
        import quotequail

        parts = quotequail.quote_html(html)
        if parts:
            replies = [chunk for is_reply, chunk in parts if is_reply]
            quoted_chunks = [chunk for is_reply, chunk in parts if not is_reply]
            if replies:
                html = replies[0]
    except Exception as exc:  # noqa: BLE001 — best-effort; continue with raw HTML
        log.debug("quotequail failed, continuing with raw HTML: %s", exc)

    soup = BeautifulSoup(html, "lxml")

    # 2. Quote containers: capture their text for the quoted zone, then remove.
    for selector in _QUOTE_SELECTORS:
        for el in soup.select(selector):
            quoted_chunks.append(str(el))
            el.decompose()

    # 3. Signatures — with the "whole body inside gmail_signature" re-parse.
    #    Skipped for outbound: the author's own signature is part of what they
    #    sent and removing it makes the stored copy read as truncated.
    if not outbound:
        sig_elements = []
        for selector in _SIGNATURE_SELECTORS:
            sig_elements.extend(soup.select(selector))
        if sig_elements:
            for el in sig_elements:
                el.decompose()
            if not soup.get_text(strip=True):
                log.debug("signature removal emptied result — re-parsing without it")
                soup = BeautifulSoup(html, "lxml")
                for selector in _QUOTE_SELECTORS:
                    for el in soup.select(selector):
                        el.decompose()

    # 4. Cutoff markers (+ all following siblings), Outlook separators, footers.
    for selector in _CUTOFF_SELECTORS:
        for el in soup.select(selector):
            for sibling in list(el.find_next_siblings()):
                quoted_chunks.append(str(sibling))
                sibling.decompose()
            el.decompose()
    _remove_outlook_separators_html(soup)
    if not outbound:
        _remove_unsubscribe_footers_html(soup)

    author_text = soup.get_text(separator="\n", strip=True)

    quoted_text = ""
    if quoted_chunks:
        qsoup = BeautifulSoup("\n".join(quoted_chunks), "lxml")
        quoted_text = qsoup.get_text(separator="\n", strip=True)
    return author_text, quoted_text


# --- public API ----------------------------------------------------------------

_QUOTED_ZONE_MAX = 4000  # chars of quoted-reply chain kept for the demoted zone


@dataclass
class CleanedEmail:
    text: str        # the author's new content, cleaned (plain text)
    quoted: str      # the meaningful quoted reply chain (plain text, clipped)
    html: str        # render-ready: author zone + <blockquote class="quoted-reply">
    snippet: str     # first ~200 chars of ``text``


def _text_to_html(text: str) -> str:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return "".join(
        "<p>" + html_mod.escape(p).replace("\n", "<br>") + "</p>" for p in paras
    )


# Tags that can execute, navigate, or restyle the page — removed outright from
# a View-original render. Everything presentational stays (the point of the
# view is formatting fidelity); the frontend additionally isolates it in a
# sandboxed iframe.
_ORIGINAL_STRIP_TAGS = (
    "script", "style", "iframe", "object", "embed", "link", "meta", "base",
    "form", "input", "button",
)


def sanitize_original_html(html: str, cid_base: str = "") -> str:
    """A View-original safety pass over a full raw email body (email-quality
    plan §3.2): scripts/embeds/on* handlers/javascript: URLs are removed,
    formatting and inline styles are KEPT (fidelity is the point), and
    ``cid:`` image references are rewritten to ``{cid_base}/{content-id}`` —
    the companion subresource endpoint that streams the inline part's bytes
    under the same ACL gate."""
    import urllib.parse

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "lxml")
    for el in soup(list(_ORIGINAL_STRIP_TAGS)):
        el.decompose()
    for el in soup.find_all(True):
        for attr in list(el.attrs):
            low = attr.lower()
            value = el.attrs[attr]
            if low.startswith("on"):
                del el.attrs[attr]
            elif low in ("href", "src", "background", "action") and str(
                value
            ).strip().lower().startswith("javascript:"):
                del el.attrs[attr]
        src = el.attrs.get("src")
        if src and str(src).strip().lower().startswith("cid:") and cid_base:
            cid = str(src).strip()[4:].strip("<>")
            el.attrs["src"] = (
                cid_base.rstrip("/") + "/" + urllib.parse.quote(cid, safe="")
            )
    body = soup.body
    if body is not None:
        return body.decode_contents()
    return str(soup)


def clean_email(
    body_text: str, body_html: str | None = None, *, outbound: bool = False
) -> CleanedEmail:
    """Clean one email body. HTML-first with a plain-text fallback.

    ``outbound=True`` = a message written by OUR user (app compose, or their
    own mailbox's sent copy): only the quoted reply history is removed; the
    signature/valediction/boilerplate heuristics — tuned for inbound mail —
    are skipped, because on authored content they truncate real paragraphs.
    """
    quoted = ""
    text = ""

    # ── HTML track ────────────────────────────────────────────────────────
    if body_html and body_html.strip():
        try:
            author_text, quoted = _html_track(body_html, outbound=outbound)
            if author_text and author_text.strip():
                text = _text_level_cleanup(author_text, outbound=outbound)
        except Exception as exc:  # noqa: BLE001 — fall back to plain text
            log.debug("HTML track failed, falling back to plain text: %s", exc)

    # ── plain-text fallback ───────────────────────────────────────────────
    if not text and body_text and body_text.strip():
        body = body_text
        try:
            from mailparser_reply import EmailReplyParser

            parsed = EmailReplyParser().parse_reply(body)
            if parsed and parsed.strip():
                if not quoted and len(body) > len(parsed):
                    quoted = body[len(parsed):].strip()  # rough: the removed tail
                body = parsed
        except Exception as exc:  # noqa: BLE001
            log.debug("mail-parser-reply failed, falling back to regex: %s", exc)
        for pattern in (_FORWARDED_HEADER, _OUTLOOK_SEPARATOR, _ON_WROTE):
            m = pattern.search(body)
            if m:
                if not quoted:
                    quoted = body[m.start():].strip()
                body = body[: m.start()].rstrip()
        text = _text_level_cleanup(body, outbound=outbound)

    if not text and (body_text or body_html):
        # Everything stripped — a quote-only reply or image-only mail. Never
        # dump the raw (quoted) body back in; a small placeholder keeps the
        # message visible as an event, with the original a click away in Gmail.
        text = "(no new text — use View original to see the full message)"

    quoted = re.sub(r"\n{3,}", "\n\n", (quoted or "").strip())[:_QUOTED_ZONE_MAX]
    html_out = _text_to_html(text)
    snippet = re.sub(r"\s+", " ", text)[:200]
    return CleanedEmail(text=text, quoted=quoted, html=html_out, snippet=snippet)
