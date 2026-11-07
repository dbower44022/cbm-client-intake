"""The chapter website's settings address and images — prds/chapter-website-plan.md, piece A.

Covers what is easy to regress: the switch answers 404 per request, the
payload keeps the shape the chapter connector reads, a page this release
cannot serve is refused on save AND reported off, a bad value never reaches
the website, cross-origin reads are allowed only for the chapter website, and
an uploaded image is checked by its own bytes.
"""

from __future__ import annotations

import base64
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import apply_overrides, get_settings
from core.settings_registry import (
    BY_KEY,
    GROUP_WEBSITE,
    WEBSITE_PAGE_SWITCHES,
    WEBSITE_PAGES_SERVED,
)
from core.settings_store import SettingsError, validate_value
from forms import info_request
from website import images as images_mod
from website.service import CONTRACT_VERSION, settings_payload
from website.store import website_image

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'

_ADMIN = {"userName": "adm", "name": "Ada", "isAdmin": True, "userId": "u1",
          "token": "t", "teams": [], "roles": []}
_STAFF = {"userName": "stf", "name": "Sam", "isAdmin": False, "userId": "u2",
          "token": "t", "teams": ["Mentor Team"], "roles": []}


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    apply_overrides({})
    yield
    apply_overrides({})
    get_settings.cache_clear()


class FakeWebsiteStore:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    async def image_meta(self):
        return {n: {k: v for k, v in r.items() if k != "data"} for n, r in self.rows.items()}

    async def get_image(self, name):
        return self.rows.get(name)

    async def put_image(self, name, data, content_type, *, actor=""):
        self.rows[name] = {"name": name, "contentType": content_type, "data": data,
                           "sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
                           "updatedAt": datetime.now(timezone.utc).isoformat(), "updatedBy": actor}
        return {k: v for k, v in self.rows[name].items() if k != "data"}

    async def delete_image(self, name):
        return self.rows.pop(name, None) is not None


def _app(monkeypatch, *, api=True, user=None, **env):
    monkeypatch.setenv("SESSION_SECRET", "s")
    monkeypatch.setenv("SETUP_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    monkeypatch.setenv("WEBSITE_API", "true" if api else "false")
    monkeypatch.setenv("APP_BASE_URL", "https://apps.example.org")
    for k, v in env.items():
        monkeypatch.setenv(k.upper(), v)
    monkeypatch.setattr("setup.router.current_user", lambda r: user)
    get_settings.cache_clear()
    app = create_app([info_request.SPEC])
    from tests.test_system_settings import FakeStore

    app.state.settings_store = FakeStore()
    app.state.job_store = None
    app.state.website_store = FakeWebsiteStore()
    return app


# --- the switch ----------------------------------------------------------------

def test_off_means_absent(monkeypatch):
    client = TestClient(_app(monkeypatch, api=False))
    assert client.get("/api/website/settings").status_code == 404
    assert client.get("/api/website/images/logo").status_code == 404


def test_the_switch_bites_per_request(monkeypatch):
    client = TestClient(_app(monkeypatch, api=False))
    assert client.get("/api/website/settings").status_code == 404
    apply_overrides({"website_api": "true"})
    assert client.get("/api/website/settings").status_code == 200


# --- the payload ---------------------------------------------------------------

def test_the_payload_has_the_shape_the_chapter_connector_reads(monkeypatch):
    body = TestClient(_app(monkeypatch)).get("/api/website/settings").json()
    assert body["version"] == CONTRACT_VERSION == 1
    assert set(body["colors"]) == {"base", "contrast", "accent-1", "accent-2", "accent-3",
                                   "accent-4", "accent-5", "accent-6"}
    assert body["colors"]["accent-1"] == "#173B60"
    assert set(body["fonts"]) == {"heading", "body"}
    assert set(body["chapter"]) >= {"name", "abbreviation", "email", "phone", "address",
                                    "ein", "paymentLink"}
    assert set(body["pages"]) == {"mentors", "events", "recordings", "partners",
                                  "sponsors", "stories"}
    assert body["logoUrl"] is None and body["headerImage"] is None


def test_the_settings_answer_may_be_cached_briefly(monkeypatch):
    resp = TestClient(_app(monkeypatch)).get("/api/website/settings")
    assert resp.headers["Cache-Control"] == "public, max-age=60"


def test_a_bad_deployment_value_never_reaches_the_website(monkeypatch):
    body = TestClient(_app(monkeypatch, website_color_base="red;}body{",
                           chapter_ein="12345", chapter_payment_url="http://x")
                      ).get("/api/website/settings").json()
    assert "base" not in body["colors"]
    assert body["chapter"]["ein"] == "" and body["chapter"]["paymentLink"] == ""


def test_a_stored_page_switch_reads_off_until_the_page_is_served():
    apply_overrides({"website_page_partners": "true", "website_page_mentors": "true"})
    payload = settings_payload(get_settings(), {}, "https://apps.example.org")
    for page in ("partners", "mentors"):
        assert payload["pages"][page] is (page in WEBSITE_PAGES_SERVED)


def test_social_links_become_label_and_address(monkeypatch):
    apply_overrides({"chapter_social_links":
                     "LinkedIn|https://www.linkedin.com/company/x, Facebook|https://facebook.com/x"})
    payload = settings_payload(get_settings(), {}, "https://a")
    assert payload["chapter"]["social"] == [
        {"label": "LinkedIn", "url": "https://www.linkedin.com/company/x"},
        {"label": "Facebook", "url": "https://facebook.com/x"},
    ]


def test_the_logo_falls_back_to_the_hosted_address_only_when_none_is_uploaded():
    apply_overrides({"organization_logo_url": "https://example.org/logo.png"})
    s = get_settings()
    assert settings_payload(s, {}, "https://a")["logoUrl"] == "https://example.org/logo.png"
    meta = {"logo": {"sha256": "ab" * 32}}
    assert settings_payload(s, meta, "https://a/")["logoUrl"] == \
        "https://a/api/website/images/logo?v=" + "ab" * 6


# --- refusals on save ------------------------------------------------------------

@pytest.mark.parametrize("page", sorted(WEBSITE_PAGE_SWITCHES))
def test_a_page_this_release_cannot_serve_is_refused(page):
    key = WEBSITE_PAGE_SWITCHES[page]
    validate_value(key, "false")
    if page in WEBSITE_PAGES_SERVED:
        validate_value(key, "true")
    else:
        with pytest.raises(SettingsError):
            validate_value(key, "true")


@pytest.mark.parametrize("key,value", [
    ("website_color_accent_1", "navy"),
    ("website_color_base", "#FFF"),
    ("website_font_body", "Arial; } body { display:none"),
    ("chapter_ein", "123456789"),
    ("chapter_email", "not an address"),
    ("chapter_payment_url", "http://buy.stripe.com/x"),
    ("website_origins", "https://example.org/path"),
    ("chapter_social_links", "LinkedIn"),
])
def test_a_bad_website_value_is_refused(key, value):
    with pytest.raises(SettingsError):
        validate_value(key, value)


@pytest.mark.parametrize("key,value", [
    ("website_color_accent_1", "#0B6E4F"),
    ("website_font_heading", "Georgia, 'Times New Roman', serif"),
    ("chapter_ein", "12-3456789"),
    ("chapter_email", "info@example.org"),
    ("chapter_payment_url", "https://buy.stripe.com/test_x"),
    ("website_origins", "https://chapter-demo.mentorsassociation.org, http://localhost:8080"),
    ("chapter_social_links", "LinkedIn|https://www.linkedin.com/company/x"),
    ("chapter_email", ""),
])
def test_a_good_website_value_is_accepted(key, value):
    validate_value(key, value)


def test_the_chapter_wide_values_sit_in_the_website_group():
    """Decision 4.2: moved from Presentation, keys unchanged."""
    for key in ("organization_name", "organization_abbreviation", "chapter_postal_address",
                "organization_logo_url", "organization_website_url", "organization_site_nav",
                "chapter_tokens_url", "website_origins", "chapter_ein"):
        assert BY_KEY[key].group == GROUP_WEBSITE, key


# --- cross-origin reads ----------------------------------------------------------

def test_only_the_chapter_website_may_read_across_origins(monkeypatch):
    client = TestClient(_app(monkeypatch, website_origins="https://chapter-demo.example.org"))
    ok = client.get("/api/website/settings", headers={"Origin": "https://chapter-demo.example.org"})
    assert ok.headers.get("access-control-allow-origin") == "https://chapter-demo.example.org"
    other = client.get("/api/website/settings", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in other.headers


def test_the_website_is_not_added_to_the_application_wide_origins(monkeypatch):
    client = TestClient(_app(monkeypatch, website_origins="https://chapter-demo.example.org"))
    resp = client.get("/healthz", headers={"Origin": "https://chapter-demo.example.org"})
    assert "access-control-allow-origin" not in resp.headers


# --- images: checking an upload ----------------------------------------------------

def test_a_png_is_accepted_by_its_bytes():
    data, kind = images_mod.decode("data:image/png;base64," + base64.b64encode(PNG).decode())
    assert data == PNG and kind == "image/png"


def test_an_svg_is_refused_with_its_reason():
    with pytest.raises(images_mod.ImageError, match="script"):
        images_mod.decode(base64.b64encode(SVG).decode())


def test_a_file_that_claims_to_be_png_but_is_not_is_refused():
    with pytest.raises(images_mod.ImageError, match="PNG, JPEG and WebP"):
        images_mod.decode("data:image/png;base64," + base64.b64encode(b"GIF89a....").decode())


def test_an_image_over_two_megabytes_is_refused():
    big = PNG + b"\x00" * (images_mod.MAX_BYTES + 1)
    with pytest.raises(images_mod.ImageError, match="2 MB"):
        images_mod.decode(base64.b64encode(big).decode())


def test_garbage_is_refused():
    with pytest.raises(images_mod.ImageError):
        images_mod.decode("%%% not base64 %%%")


# --- images: upload in System Settings, serve publicly ------------------------------

def test_upload_is_admin_only(monkeypatch):
    client = TestClient(_app(monkeypatch, user=_STAFF))
    resp = client.put("/setup/api/website/images/logo", json={"data": base64.b64encode(PNG).decode()})
    assert resp.status_code == 403


def test_upload_serve_and_remove(monkeypatch):
    app = _app(monkeypatch, user=_ADMIN)
    client = TestClient(app)
    body = client.put("/setup/api/website/images/logo",
                      json={"data": "data:image/png;base64," + base64.b64encode(PNG).decode()}).json()
    logo = next(i for i in body["images"] if i["name"] == "logo")
    assert logo["set"] is True and logo["contentType"] == "image/png"

    settings = client.get("/api/website/settings").json()
    assert settings["logoUrl"].startswith("https://apps.example.org/api/website/images/logo?v=")

    served = client.get("/api/website/images/logo")
    assert served.status_code == 200 and served.content == PNG
    assert served.headers["content-type"] == "image/png"
    assert served.headers["x-content-type-options"] == "nosniff"
    again = client.get("/api/website/images/logo", headers={"If-None-Match": served.headers["etag"]})
    assert again.status_code == 304

    preview = client.get("/setup/api/website/images/logo")
    assert preview.status_code == 200 and preview.content == PNG

    body = client.delete("/setup/api/website/images/logo").json()
    assert next(i for i in body["images"] if i["name"] == "logo")["set"] is False
    assert client.get("/api/website/images/logo").status_code == 404


def test_an_svg_upload_answers_the_reason(monkeypatch):
    client = TestClient(_app(monkeypatch, user=_ADMIN))
    resp = client.put("/setup/api/website/images/header", json={"data": base64.b64encode(SVG).decode()})
    assert resp.status_code == 400 and "script" in resp.json()["detail"]


def test_an_unknown_image_name_is_404(monkeypatch):
    client = TestClient(_app(monkeypatch, user=_ADMIN))
    assert client.put("/setup/api/website/images/favicon",
                      json={"data": base64.b64encode(PNG).decode()}).status_code == 404
    assert client.get("/api/website/images/favicon").status_code == 404


# --- the table matches its migration -------------------------------------------------

def test_the_image_table_declares_every_column_the_migration_creates():
    text = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
            / "0042_website_image.py").read_text(encoding="utf-8")
    migrated = set(re.findall(r'sa\.Column\("(\w+)"', text.split("def downgrade", 1)[0]))
    assert migrated == {c.name for c in website_image.columns}
