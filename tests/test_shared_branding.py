"""Whose name the product carries — and the guard that keeps it configurable.

Phase 0 of ``prds/multi-chapter-deployment-plan.md`` removed the literal string
"Cleveland Business Mentors" from 18 frontend HTML files (48 occurrences) plus
four surfaces outside HTML, replacing it with the ``{{org}}`` token substituted
server-side by ``core/branding.py``.

This file exists because that decays otherwise. The load-bearing tests are:

* :func:`test_no_frontend_file_hardcodes_the_organisation_name` — the guard. A
  new page that types the name instead of the token fails here.
* :func:`test_every_branded_page_carries_the_token` — the other half. A new page
  that omits the name entirely still has to declare its branding, or the next
  chapter gets an anonymous tab.
* :func:`test_a_default_deployment_still_says_cleveland` — the safety property.
  With nothing configured, the served page is what it always was.
* :func:`test_brand_as_identifier_is_left_alone` — the fence. ``--cbm-*``,
  ``cbm-`` classes and ``window.CBM*`` are identifiers, not content; renaming
  them is 3500+ edits for zero benefit and breaks two live website contracts.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.branding import MODE_HTML, MODE_JS, MODE_TEXT, render
from core.config import Settings, get_settings
from forms import client_intake, info_request, volunteer

ROOT = Path(__file__).resolve().parent.parent

#: Directories holding pages this app serves. ``wp-plugin`` and
#: ``events/frontend/preview*.css`` are deliberately absent — they are verbatim
#: copies of a specific WordPress site and are retired by plan phase 4, not
#: parameterized (plan § *Phase 0*, item 8).
APP_FRONTEND_ROOTS = (
    "analytics", "assignments", "directory", "events", "forms", "mentoradmin",
    "mentorprofile", "myemail", "ops", "portal", "sessions", "setup",
    "frontend/shared",
)

#: The name, in the form that must never appear in a shipped frontend file.
ORG_LITERAL = "Cleveland Business Mentors"

#: Files exempt from the guard, each for a stated reason. Keep this list SHORT
#: and keep the reasons true — an exemption without a reason is how the guard
#: stops meaning anything.
GUARD_EXEMPT = {
    # PROVENANCE, not identity: the header records which site the palette was
    # extracted from and when. Deleting that would lose the audit trail; the
    # values themselves are the base layer a chapter overrides.
    "frontend/shared/tokens.css",
}

#: `mentorprofile/frontend/` reproduces Cleveland's own Elementor page
#: byte-for-byte so a mentor's preview is an exact rendering of their public
#: profile — plan ruling 8 / phase 4 retire it rather than parameterize it. The
#: page's OWN chrome (title, footer) is still branded; only the copied block
#: keeps its clevelandbusinessmentors.org links, which are URLs and so do not
#: match ORG_LITERAL. No exemption is needed, and that is worth asserting.
VERBATIM_WEBSITE_COPY = "mentorprofile/frontend/index.html"

#: The SECOND name, RULED A COPY BUG (Doug, 2026-08-20) and swept into the
#: token. It reached the four public intake forms through commit 7cc6a8f, which
#: rebranded SCORE wording on the volunteer form; the partner, sponsor and
#: info-request forms then copied the phrasing. The organisation is
#: "Cleveland Business Mentors" — the domain, the mailbox display name and every
#: title and footer say so. "Cleveland Business Mentoring" survives only as the
#: name of the process-definition REPOSITORY, which is not public-facing copy.
SECOND_NAME = "Cleveland Business Mentoring"


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _frontend_files(*suffixes: str) -> list[Path]:
    out: list[Path] = []
    for root in APP_FRONTEND_ROOTS:
        for suffix in suffixes:
            out.extend((ROOT / root).rglob(f"*{suffix}"))
    return sorted(p for p in out if "/vendor/" not in str(p))


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


# --- the substitution itself ------------------------------------------------

def test_the_token_substitutes():
    s = Settings(organization_name="Akron Business Mentors")
    assert render("<title>{{org}} — Home</title>", s) == (
        "<title>Akron Business Mentors — Home</title>"
    )


def test_the_default_is_cleveland():
    assert Settings().organization_name == ORG_LITERAL
    assert render("{{org}}", Settings()) == ORG_LITERAL


def test_the_value_is_escaped_for_where_it_lands():
    """The name is settable from /setup and lands on PUBLIC intake forms, so it
    is escaped for its context rather than trusted. An admin who can
    reconfigure the platform is not thereby handed a stored-XSS vector aimed at
    members of the public."""
    s = Settings(organization_name='Acme <script>alert(1)</script> & Co')
    html = render("<title>{{org}}</title>", s, MODE_HTML)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html and "&amp;" in html

    js = render('var name = "{{org}}";', s, MODE_JS)
    assert "</script>" not in js and "<script>" not in js
    assert "\\u003c" in js and "\\u003e" in js
    inner = js[js.index('"') + 1:js.rindex('"')]
    assert '"' not in inner, "the value could close its own string literal"

    # Plain text — an LLM prompt, a CRM field, an email body — is not markup.
    assert render("{{org}}", s, MODE_TEXT) == 'Acme <script>alert(1)</script> & Co'


def test_a_value_containing_a_token_does_not_recurse():
    s = Settings(organization_name="{{org}} Ltd")
    assert render("{{org}}", s, MODE_TEXT) == "{{org}} Ltd"


# --- the guard --------------------------------------------------------------

def test_no_frontend_file_hardcodes_the_organisation_name():
    """THE GUARD. A page that types the name instead of `{{org}}` fails here.

    Without this, Phase 0 decays with the next feature — which is exactly how
    18 files came to carry it in the first place."""
    offenders = []
    for path in _frontend_files(".html", ".js", ".css"):
        rel = _rel(path)
        if rel in GUARD_EXEMPT:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if ORG_LITERAL in text:
            lines = [i for i, l in enumerate(text.splitlines(), 1) if ORG_LITERAL in l]
            offenders.append(f"{rel}: lines {lines}")
    assert not offenders, (
        "hardcoded organisation name — use the {{org}} token instead "
        "(core/branding.py):\n  " + "\n  ".join(offenders)
    )


def test_the_second_name_does_not_come_back():
    """The product briefly said "Cleveland Business Mentoring" in seven places,
    all body prose on the public forms. Doug ruled it a copy bug (2026-08-20)
    and it was swept into the token; the organisation is "…Mentors". This fails
    if it reappears, which is how a copied form introduced it the first time."""
    offenders = []
    for path in _frontend_files(".html", ".js", ".css"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if SECOND_NAME in text:
            lines = [i for i, l in enumerate(text.splitlines(), 1) if SECOND_NAME in l]
            offenders.append(f"{_rel(path)}: lines {lines}")
    assert not offenders, (
        f'"{SECOND_NAME}" is not the organisation\'s name — it names the '
        "process-definition repository. Use the {{org}} token:\n  "
        + "\n  ".join(offenders)
    )


def test_every_branded_page_carries_the_token():
    """The other half of the guard: a page must SAY whose it is.

    A new page whose title omits the organisation entirely passes the guard
    above while still being wrong — the next chapter gets an anonymous tab."""
    missing = []
    for path in _frontend_files(".html"):
        rel = _rel(path)
        if rel in GUARD_EXEMPT or "/preview" in rel:
            continue  # preview*.html are developer harnesses, not served pages
        text = path.read_text(encoding="utf-8")
        title = re.search(r"<title>(.*?)</title>", text, re.S)
        if title is None:
            continue  # a fragment, not a page
        if "{{org}}" not in title.group(1):
            missing.append(f"{rel}: <title> has no {{{{org}}}}")
        if 'name="cbm-org"' not in text:
            missing.append(f'{rel}: no <meta name="cbm-org"> for page scripts')
    assert not missing, "\n  " + "\n  ".join(missing)


def test_brand_as_identifier_is_left_alone():
    """THE FENCE. `--cbm-*`, `cbm-` classes and `window.CBM*` are IDENTIFIERS,
    not content — never shown to a user, 3500+ occurrences, and two of them are
    live contracts with a chapter's WordPress site (the events renderer's class
    names and `CBMEvents.config`). De-Clevelanding must not touch them, and this
    test is here so a later session does not "finish the job"."""
    tokens_css = (ROOT / "frontend" / "shared" / "tokens.css").read_text()
    assert "--cbm-navy" in tokens_css and "--cbm-gold" in tokens_css
    assert (ROOT / "frontend" / "shared" / "busy.js").read_text().count("CBMBusy") > 0
    assert "data-cbm-year" in (ROOT / "frontend" / "shared" / "footer.js").read_text()
    plugin = (ROOT / "wp-plugin" / "cbm-events" / "assets" / "cbm-events.js")
    if plugin.is_file():
        assert "CBMEvents" in plugin.read_text()


# --- what actually gets served ---------------------------------------------

def _public_app(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    return TestClient(create_app([info_request.SPEC, volunteer.SPEC, client_intake.SPEC]))


PUBLIC_PAGES = ["/info-request/", "/volunteer/", "/client-intake/"]


@pytest.mark.parametrize("page", PUBLIC_PAGES)
def test_a_default_deployment_still_says_cleveland(monkeypatch, page):
    """THE SAFETY PROPERTY. Cleveland is the default, not a special case — which
    is what makes Phase 0 shippable on `main` with deploy_on_push on three apps
    and no feature flag."""
    client = _public_app(monkeypatch)
    body = client.get(page).text
    assert ORG_LITERAL in body
    assert "{{" not in body, "an unsubstituted token reached the browser"


@pytest.mark.parametrize("page", PUBLIC_PAGES)
def test_a_configured_deployment_says_its_own_name(monkeypatch, page):
    client = _public_app(monkeypatch, ORGANIZATION_NAME="Akron Business Mentors")
    body = client.get(page).text
    assert "Akron Business Mentors" in body
    assert ORG_LITERAL not in body
    assert "{{" not in body


def test_the_page_exposes_the_name_to_its_scripts(monkeypatch):
    """`<meta name="cbm-org">` rather than a /healthz fetch: the two scripts
    that need the name at runtime (the portal birthday card, the directory
    mentor page's title) read it SYNCHRONOUSLY, with no race and no flicker."""
    client = _public_app(monkeypatch, ORGANIZATION_NAME="Akron Business Mentors")
    body = client.get("/volunteer/").text
    assert '<meta name="cbm-org" content="Akron Business Mentors" />' in body


def test_healthz_reports_the_organisation(monkeypatch):
    client = _public_app(monkeypatch, ORGANIZATION_NAME="Akron Business Mentors")
    data = client.get("/healthz").json()
    assert data["organization"] == "Akron Business Mentors"


def test_html_is_revalidatable_and_the_etag_tracks_the_name(monkeypatch):
    """Rewriting on serve must not break conditional requests, and the ETag has
    to change when the name does — otherwise a browser holding the previous
    chapter's name would never be told."""
    client = _public_app(monkeypatch)
    first = client.get("/volunteer/")
    etag = first.headers["etag"]
    again = client.get("/volunteer/", headers={"If-None-Match": etag})
    assert again.status_code == 304

    client = _public_app(monkeypatch, ORGANIZATION_NAME="Akron Business Mentors")
    assert client.get("/volunteer/").headers["etag"] != etag


def test_assets_that_carry_no_token_are_served_untouched(monkeypatch):
    client = _public_app(monkeypatch)
    r = client.get("/shared/tokens.css")
    assert r.status_code == 200
    assert "--cbm-navy" in r.text


def test_the_dev_form_index_is_branded(monkeypatch):
    """The dry-run dev app's root is server-RENDERED, not a static file — a
    separate code path, and one that carried the literal name."""
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    client = _public_app(monkeypatch, ORGANIZATION_NAME="Akron Business Mentors")
    body = client.get("/").text
    assert "Akron Business Mentors" in body
    assert ORG_LITERAL not in body


def test_the_shared_sender_name_falls_back_to_the_organisation():
    """`ops_mailbox_name` no longer repeats the organisation's name; a chapter
    says who it is once."""
    assert Settings().sender_display_name == ORG_LITERAL
    assert Settings(organization_name="Akron BM").sender_display_name == "Akron BM"
    assert Settings(ops_mailbox_name="CBM Info").sender_display_name == "CBM Info"


# --- the chapter design-token override --------------------------------------

def test_no_chapter_stylesheet_is_injected_by_default(monkeypatch):
    """Byte-identical by default: an unset override injects nothing at all."""
    client = _public_app(monkeypatch)
    body = client.get("/volunteer/").text
    assert body.count("<link rel=\"stylesheet\"") == (
        (ROOT / "forms" / "volunteer" / "frontend" / "index.html")
        .read_text().count("<link rel=\"stylesheet\"")
    )


def test_the_chapter_stylesheet_loads_after_the_base_tokens(monkeypatch):
    """The cascade is the mechanism: an override can only shadow the properties
    it names, so it cannot break the base tokens."""
    client = _public_app(monkeypatch, CHAPTER_TOKENS_URL="/chapter/akron.css")
    body = client.get("/volunteer/").text
    assert "/chapter/akron.css" in body
    assert body.index("/shared/tokens.css") < body.index("/chapter/akron.css")


def test_the_chapter_stylesheet_url_is_escaped(monkeypatch):
    client = _public_app(
        monkeypatch, CHAPTER_TOKENS_URL='x.css" onload="alert(1)'
    )
    body = client.get("/volunteer/").text
    assert 'onload="alert(1)"' not in body
    assert "&quot;" in body


def test_changing_the_override_changes_the_etag(monkeypatch):
    plain = _public_app(monkeypatch).get("/volunteer/").headers["etag"]
    themed = _public_app(
        monkeypatch, CHAPTER_TOKENS_URL="/chapter/akron.css"
    ).get("/volunteer/").headers["etag"]
    assert plain != themed


def test_the_verbatim_website_copy_keeps_its_links_but_not_the_name():
    """The mentor-profile preview is Cleveland's page by definition and phase 4
    retires it. Its own chrome is branded anyway, so it needs no exemption —
    if that ever stops being true, this says so rather than a silent allowlist
    growing."""
    text = (ROOT / VERBATIM_WEBSITE_COPY).read_text()
    assert ORG_LITERAL not in text, "the page chrome regressed"
    assert "{{org}}" in text
    assert "clevelandbusinessmentors.org" in text, (
        "the verbatim copy lost its links — it is supposed to reproduce the "
        "live page exactly until plan phase 4 retires it"
    )
