"""Whose name the product carries.

Every page names its owner — in the ``<title>``, in the footer, and (on the
public forms) in prose a member of the public reads. Until v0.205.0 that name
was the literal string "Cleveland Business Mentors", baked into 18 HTML files in
48 places, so the software told every user it belonged to Cleveland whatever
deployment they were looking at.

The mechanism here is deliberately the smallest one that removes the flicker:

* the markup carries a **token**, ``{{org}}``;
* the token is substituted **server-side, as the file is served**, by
  :class:`BrandedStaticFiles`;
* the value is one ordinary setting, ``ORGANIZATION_NAME``, defaulting to
  Cleveland.

**Why server-side rather than a ``data-`` attribute filled by JS.** The existing
``footer.js`` pattern (a ``data-cbm-*`` attribute, a value from ``/healthz``, one
shared script) is the right shape for the *version*, which nobody reads at first
paint. It is the wrong shape for the organisation's name: the ``<title>`` would
flicker in the browser tab and the public forms' body prose would visibly repaint
after the ``/healthz`` round-trip. Substituting on serve costs one small read per
HTML file per deploy and flickers nowhere.

**The safety property.** With no configuration set, the rendered bytes are
byte-identical to what the same page served before this module existed —
Cleveland is the default, not a special case. That is what makes the change
shippable on ``main`` with ``deploy_on_push: true`` on three apps and no feature
flag. A guard test (``tests/test_shared_branding.py``) holds both halves: no
frontend file may carry the literal name again, and every served page must come
out with no token left in it.

**Brand-as-identifier is not touched and must never be.** ``window.CBM*``,
``--cbm-*``, the ``cbm-`` class prefix and the ``data-cbm-*`` attributes are
identifiers, not content — 12 namespaces, 52 custom properties across 1223 uses,
2298 class occurrences, and two of them are live contracts with a chapter's
WordPress site. The prefix names the software, not the chapter. See
``prds/chapter-network/phase-0-decleveland.md``.
"""

from __future__ import annotations

import hashlib
import os
import stat as stat_module
import time
from email.utils import formatdate, parsedate_to_datetime
from typing import TYPE_CHECKING, Optional

from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

if TYPE_CHECKING:  # pragma: no cover
    from core.config import Settings

#: The token vocabulary, and all of it. ONE token, one meaning: the display name
#: of the organisation running this deployment. It is one rather than two because
#: Doug ruled (2026-08-20) that the "Cleveland Business Mentoring" wording on four
#: public forms was a copy bug, not a second brand. Kept as a table rather than an
#: f-string so a genuinely new token is a one-line addition here and nowhere else.
TOKEN_ORG = "{{org}}"
TOKEN_POLICY_CLIENT_CONDUCT = "{{policyClientConduct}}"
TOKEN_POLICY_MENTOR_ETHICS = "{{policyMentorEthics}}"
TOKEN_POLICY_TERMS = "{{policyTerms}}"
TOKEN_POLICY_PRIVACY = "{{policyPrivacy}}"


#: How a value is escaped for the place it lands in. The value is CONFIGURATION,
#: settable from ``/setup`` by an EspoCRM admin, and it is substituted into the
#: **public** intake forms — so it is escaped for its context, not trusted. An
#: admin can already reconfigure the platform; that is not a reason to hand them
#: a stored-XSS vector aimed at members of the public.
MODE_HTML = "html"
MODE_JS = "js"
MODE_TEXT = "text"


def tokens(settings: "Settings") -> dict[str, str]:
    """The substitution table for one deployment, values unescaped."""
    return {
        TOKEN_ORG: settings.organization_name,
        TOKEN_POLICY_CLIENT_CONDUCT: settings.policy_client_conduct_url,
        TOKEN_POLICY_MENTOR_ETHICS: settings.policy_mentor_ethics_url,
        TOKEN_POLICY_TERMS: settings.policy_terms_url,
        TOKEN_POLICY_PRIVACY: settings.policy_privacy_url,
    }


def _escape(value: str, mode: str) -> str:
    if mode == MODE_HTML:
        # quote=True: the token also appears inside attribute values
        # (<meta name="cbm-org" content="{{org}}">).
        from html import escape

        return escape(value, quote=True)
    if mode == MODE_JS:
        # The inside of a JS string literal, with < > escaped too so a value
        # can never close a <script> element.
        import json

        return (
            json.dumps(value)[1:-1]
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
        )
    return value


def render(text: str, settings: "Settings", mode: str = MODE_HTML) -> str:
    """Substitute every branding token in ``text``.

    Cheap and deliberately dumb — a literal replace per token, no template
    engine, no expression evaluation. Values are never re-scanned for tokens, so
    a value containing ``{{org}}`` cannot recurse.

    ``mode`` says what the result is: markup (default), the inside of a JS
    string literal, or plain text (an email body, a CRM field, an LLM prompt).
    """
    for token, value in tokens(settings).items():
        text = text.replace(token, _escape(value, mode))
    return text


#: Where the chapter override is threaded into the cascade: immediately after
#: the base tokens, so it wins on the properties it names and nothing else.
BASE_TOKENS_HREF = "/shared/tokens.css"


def render_page(html: str, settings: "Settings") -> str:
    """Render one HTML page: substitute tokens, then thread in the chapter's own
    ``tokens.css`` override if this deployment has one.

    Injection rather than a per-page placeholder, deliberately — a placeholder
    would have to be added to all 18 pages and remembered on the nineteenth,
    which is the failure mode Phase 0 exists to end. With
    ``chapter_tokens_url`` empty (Cleveland, and every deployment today) nothing
    is injected and the output is the substitution alone.
    """
    html = render(html, settings, MODE_HTML)
    href = (settings.chapter_tokens_url or "").strip()
    if not href:
        return html
    from html import escape

    marker = f'href="{BASE_TOKENS_HREF}"'
    idx = html.find(marker)
    if idx < 0:
        return html  # a page that does not use the design tokens has nothing to override
    end = html.find(">", idx)
    if end < 0:
        return html
    link = f'\n  <link rel="stylesheet" href="{escape(href, quote=True)}" />'
    return html[: end + 1] + link + html[end + 1 :]


def brand_key(settings: "Settings") -> str:
    """A short stable key for the current branding, for cache invalidation.

    Changing ``ORGANIZATION_NAME`` at runtime (via ``/setup``) changes this,
    which drops the rendered-HTML cache and the ETags derived from it — so a
    browser holding the previous name revalidates rather than keeping it.
    """
    parts = [f"{k}={v}" for k, v in sorted(tokens(settings).items())]
    parts.append(f"chapter_tokens_url={settings.chapter_tokens_url}")
    joined = "\x1f".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]


#: The current branding and when it last changed. Rewriting on serve means a
#: page's content can change without its FILE changing, so ``Last-Modified`` has
#: to move when the branding does — otherwise a conditional request is told
#: "unchanged" and keeps showing the previous organisation's name.
#:
#: This matters because **DO's edge strips the ETag from HTML responses** (it
#: survives on assets served straight from disk), so ``If-Modified-Since`` is
#: the only conditional request that actually reaches us in production. A
#: process restart resets this to "now": one extra full response per page, then
#: normal revalidation. Chattier for one request, never stale.
_BRAND_STATE: dict[str, float | str | None] = {"key": None, "epoch": 0.0}


def _brand_epoch(key: str) -> float:
    """A timestamp that moves forward on every CHANGE of branding.

    Strictly increasing, and deliberately not a per-key memo: reverting to a
    previously-used name is a change like any other, and a remembered older
    timestamp would let a browser holding the *newer* name be told "unchanged"
    and keep showing it.

    ``+ 1.0`` because HTTP dates have one-second resolution — two renames inside
    the same second would otherwise compare equal and 304.
    """
    if _BRAND_STATE["key"] != key:
        _BRAND_STATE["epoch"] = max(time.time(), float(_BRAND_STATE["epoch"]) + 1.0)
        _BRAND_STATE["key"] = key
    return float(_BRAND_STATE["epoch"])


class BrandedStaticFiles(StaticFiles):
    """``StaticFiles`` that substitutes branding tokens in ``.html`` responses.

    Only HTML is rewritten. JS and CSS are served untouched — they are the bulk
    of the bytes, they are aggressively cached, and the two scripts that need
    the name at runtime read it from the ``<meta name="cbm-org">`` the rewrite
    fills in, synchronously, with no fetch and no race.

    ``file_response`` is the override point rather than ``get_response`` because
    it is the single choke point through which every real file is served,
    including the ``html=True`` directory-index resolution.
    """

    def __init__(self, *args, settings_provider=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # A callable, not a captured Settings: the override layer mutates the
        # settings object in place, so re-reading per request is what lets a
        # /setup change take effect without a redeploy.
        if settings_provider is None:
            from core.config import get_settings as settings_provider  # noqa: N813
        self._settings_provider = settings_provider
        self._cache: dict[tuple, tuple[bytes, str]] = {}
        #: Files checked once and found to contain no token — served normally.
        self._no_tokens: set[tuple] = set()

    def file_response(
        self,
        full_path,
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        if status_code == 200:
            mode = self._mode_for(str(full_path))
            if mode is not None:
                branded = self._branded(full_path, stat_result, scope, mode)
                if branded is not None:
                    return branded
        return super().file_response(full_path, stat_result, scope, status_code)

    @staticmethod
    def _mode_for(path: str) -> Optional[str]:
        """Which files may carry tokens, and how their values must be escaped.

        Vendored assets are excluded outright — they are third-party code we do
        not rewrite, and jodit.min.js is 800KB we would otherwise read to find
        no tokens in it. A `.js` file with no token falls through to the normal
        streamed `FileResponse`, so extending this costs nothing on the files
        that do not use it.
        """
        if "/vendor/" in path:
            return None
        if path.endswith(".html"):
            return MODE_HTML
        if path.endswith(".js"):
            return MODE_JS
        return None

    # -- internals ----------------------------------------------------------

    def _branded(
        self, full_path, stat_result: os.stat_result, scope: Scope, mode: str
    ) -> Optional[Response]:
        if not stat_module.S_ISREG(stat_result.st_mode):
            return None
        settings = self._settings_provider()
        key = (
            str(full_path),
            stat_result.st_mtime_ns,
            stat_result.st_size,
            brand_key(settings),
        )
        if key in self._no_tokens:
            return None  # known token-free: stream it as StaticFiles would
        hit = self._cache.get(key)
        if hit is None:
            try:
                raw = open(full_path, "rb").read().decode("utf-8")
            except (OSError, UnicodeDecodeError):
                # Unreadable or not really text — let StaticFiles handle it
                # exactly as it would have. Branding must never 500 a page.
                return None
            if not any(tok in raw for tok in tokens(settings)):
                # No tokens: hand it back to StaticFiles so it keeps its normal
                # streamed response, ETag and Range support.
                self._no_tokens.add(key)
                return None
            rendered = render_page(raw, settings) if mode == MODE_HTML else render(
                raw, settings, mode
            )
            body = rendered.encode("utf-8")
            etag = '"' + hashlib.md5(body, usedforsecurity=False).hexdigest() + '"'
            hit = (body, etag)
            # One entry per HTML file per deploy; the app has 18 of them.
            self._cache[key] = hit
        body, etag = hit

        # The later of the file's own mtime and when this process first saw this
        # branding — see _BRAND_FIRST_SEEN.
        modified = max(stat_result.st_mtime, _brand_epoch(brand_key(settings)))
        headers = {
            "content-type": (
                "text/html; charset=utf-8" if mode == MODE_HTML
                else "text/javascript; charset=utf-8"
            ),
            "content-length": str(len(body)),
            "etag": etag,
            "last-modified": formatdate(modified, usegmt=True),
        }
        request_headers = Headers(scope=scope)
        inm = request_headers.get("if-none-match")
        if inm is not None:
            fresh = _etag_matches(inm, etag)
        else:
            fresh = _not_modified_since(
                request_headers.get("if-modified-since"), modified
            )
        if fresh:
            headers.pop("content-length")
            return Response(status_code=304, headers=headers)
        if scope["method"] == "HEAD":
            return Response(b"", headers=headers)
        return Response(body, headers=headers)


def _etag_matches(if_none_match: Optional[str], etag: str) -> bool:
    """RFC 9110 §13.1.2, to the depth StaticFiles itself implements it."""
    if not if_none_match:
        return False
    if if_none_match.strip() == "*":
        return True
    for candidate in if_none_match.split(","):
        candidate = candidate.strip()
        if candidate.startswith("W/"):
            candidate = candidate[2:]
        if candidate == etag:
            return True
    return False


def _not_modified_since(if_modified_since: Optional[str], modified: float) -> bool:
    """RFC 9110 §13.1.3. Consulted only when the request sent no ETag — an
    ``If-None-Match`` that fails is a definite "changed" and must not then be
    second-guessed by a date."""
    if not if_modified_since:
        return False
    try:
        since = parsedate_to_datetime(if_modified_since).timestamp()
    except (TypeError, ValueError):
        return False
    # HTTP dates have one-second resolution; compare truncated to match.
    return int(modified) <= int(since)
