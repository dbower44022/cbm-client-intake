"""The event graphic — upload, the public image proxy, and the publish gate.

The gate is the point of these tests. `CEvent` doubles as CBM's org calendar,
so an image route keyed on anything other than a published event would be a way
to read attachments that are not meant to be public.
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from events import config as cfg
from events import service
from forms import info_request

from tests.test_events_public import FakeEspo, build
from tests.test_events_service import make_event

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class GraphicEspo(FakeEspo):
    """FakeEspo plus the attachment calls the graphic path needs."""

    def __init__(self, events=None, attachment=(b"IMAGEBYTES", "image/png"), **kw):
        super().__init__(events=events, **kw)
        self.attachment = attachment
        self.uploaded = []
        self.updates = []
        self.downloaded = []

    async def upload_attachment(self, *, filename, content_type, data_base64,
                                related_type, field):
        self.uploaded.append(
            {"filename": filename, "contentType": content_type,
             "relatedType": related_type, "field": field}
        )
        return "att-1"

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        for row in self.events:
            if row.get("id") == record_id:
                row.update(payload)
        return {"id": record_id}

    async def get(self, entity, record_id, *, select=None):
        for row in self.events:
            if row.get("id") == record_id:
                return row
        return None

    async def download_attachment(self, attachment_id):
        self.downloaded.append(attachment_id)
        return self.attachment


# --- the payload -------------------------------------------------------------


def test_image_url_is_blank_without_a_graphic():
    assert service.public_image_url(make_event()) == ""


def test_image_url_points_at_this_app_and_carries_a_version():
    event = make_event(eventGraphicId="abcdef1234567890")
    url = service.public_image_url(event, base_url="https://apps.example.org")
    assert url.startswith("https://apps.example.org/api/events/grant-writing-basics/image")
    # The version is what lets the response be cached hard yet change when the
    # picture is replaced.
    assert "v=abcdef123456" in url


def test_image_url_is_relative_without_an_app_base_url():
    event = make_event(eventGraphicId="abc")
    assert service.public_image_url(event).startswith("/api/events/")


def test_graphic_wins_over_the_youtube_thumbnail():
    """An uploaded card image beats a derived video frame — and it is the ONLY
    image an upcoming event can have."""
    event = make_event(
        eventGraphicId="abc",
        recordingUrl="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    )
    payload = service.public_event(event, api_base_url="https://apps.example.org")
    assert payload["imageUrl"]
    assert payload["thumbnailUrl"]          # still offered as the fallback
    assert payload["imageUrl"] != payload["thumbnailUrl"]


def test_recordings_carry_the_image_too():
    event = make_event(
        eventGraphicId="abc",
        recordingUrl="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    )
    assert service.public_recording(event, api_base_url="https://x.test")["imageUrl"]


# --- the public route --------------------------------------------------------


def _public_app(monkeypatch, events, **kw):
    monkeypatch.setenv("APP_BASE_URL", "https://apps.example.org")
    client, _ = build(monkeypatch, events=events, **kw)
    fake = GraphicEspo(events=events)
    client.app.state.events_client_factory = lambda: fake
    return client, fake


def test_public_image_served_for_a_published_event(monkeypatch):
    events = [make_event(eventGraphicId="att-1")]
    client, fake = _public_app(monkeypatch, events)
    resp = client.get("/api/events/grant-writing-basics/image")
    assert resp.status_code == 200
    assert resp.content == b"IMAGEBYTES"
    assert resp.headers["content-type"].startswith("image/png")


def test_public_image_404s_for_an_unpublished_event(monkeypatch):
    """The publish gate, which is the whole reason this route is keyed on the
    slug rather than an attachment id."""
    events = [make_event(publishToWebsite=False, eventGraphicId="att-1")]
    client, fake = _public_app(monkeypatch, events)
    assert client.get("/api/events/grant-writing-basics/image").status_code == 404
    assert fake.downloaded == []      # never even asked the CRM for the bytes


def test_public_image_404s_for_a_cancelled_event(monkeypatch):
    events = [make_event(status=cfg.STATUS_CANCELLED, eventGraphicId="att-1")]
    client, _ = _public_app(monkeypatch, events)
    assert client.get("/api/events/grant-writing-basics/image").status_code == 404


def test_public_image_404s_when_there_is_no_graphic(monkeypatch):
    client, _ = _public_app(monkeypatch, [make_event()])
    assert client.get("/api/events/grant-writing-basics/image").status_code == 404


def test_public_image_404s_for_an_unknown_slug(monkeypatch):
    client, _ = _public_app(monkeypatch, [make_event(eventGraphicId="att-1")])
    assert client.get("/api/events/nope/image").status_code == 404


def test_image_is_never_cached_immutably(monkeypatch):
    """Availability here is REVOCABLE — unpublishing must take the image
    offline. v0.191.0 sent `max-age=604800, immutable` on the versioned URL, so
    a browser kept serving the picture for a week after the event was
    unpublished, never asking the origin again. The `?v=` proves the content is
    unchanged; it says nothing about whether you are still allowed to see it."""
    events = [make_event(eventGraphicId="att-1")]
    client, _ = _public_app(monkeypatch, events, cache_seconds=60)
    for url in ("/api/events/grant-writing-basics/image?v=att-1",
                "/api/events/grant-writing-basics/image"):
        cache_control = client.get(url).headers["cache-control"]
        assert "immutable" not in cache_control
        assert "must-revalidate" in cache_control
        assert "max-age=60" in cache_control


def test_image_ttl_follows_the_public_cache_setting(monkeypatch):
    events = [make_event(eventGraphicId="att-1")]
    client, _ = _public_app(monkeypatch, events, cache_seconds=0)
    header = client.get("/api/events/grant-writing-basics/image").headers["cache-control"]
    assert "max-age=0" in header


def test_image_route_absent_when_the_public_api_is_off(monkeypatch):
    events = [make_event(eventGraphicId="att-1")]
    client, _ = _public_app(monkeypatch, events, public_api=False)
    assert client.get("/api/events/grant-writing-basics/image").status_code == 404


# --- the service write path --------------------------------------------------


async def test_upload_binds_the_attachment_to_the_event_field():
    fake = GraphicEspo(events=[make_event()])
    await service.set_event_graphic(
        fake, "ev1", filename="card.png", content_type="image/png", data_base64=PNG
    )
    assert fake.uploaded[0]["relatedType"] == cfg.EVENT
    assert fake.uploaded[0]["field"] == cfg.GRAPHIC_FIELD
    assert fake.updates[0][2] == {"eventGraphicId": "att-1"}


async def test_upload_rejects_a_non_image():
    fake = GraphicEspo(events=[make_event()])
    with pytest.raises(service.EventError) as exc:
        await service.set_event_graphic(
            fake, "ev1", filename="virus.pdf",
            content_type="application/pdf", data_base64=PNG,
        )
    assert "JPEG" in str(exc.value)
    assert fake.uploaded == []


async def test_upload_rejects_an_oversized_image():
    fake = GraphicEspo(events=[make_event()])
    with pytest.raises(service.EventError) as exc:
        await service.set_event_graphic(
            fake, "ev1", filename="huge.png", content_type="image/png",
            data_base64="A" * (cfg.MAX_IMAGE_B64_CHARS + 1),
        )
    assert "too large" in str(exc.value)


async def test_clear_removes_the_link():
    fake = GraphicEspo(events=[make_event(eventGraphicId="att-1")])
    await service.clear_event_graphic(fake, "ev1")
    assert fake.updates[0][2] == {"eventGraphicId": None}


async def test_get_returns_none_without_a_graphic():
    fake = GraphicEspo(events=[make_event()])
    assert await service.get_event_graphic(fake, "ev1") is None


# --- the editor spec ---------------------------------------------------------


def test_graphic_is_declared_but_not_generically_writable():
    """It must be visible to the editor (so the upload control renders) yet
    stay out of the update whitelist — a file field can't ride the field PUT."""
    spec = next(f for f in cfg.EVENT_FIELDS if f.name == cfg.GRAPHIC_FIELD)
    assert spec.type == "image" and spec.app_managed
    assert cfg.GRAPHIC_FIELD not in cfg.EVENT_EDIT_NAMES


# --- the website preview -----------------------------------------------------


def _staff_app(monkeypatch, **kw):
    """The preview and the plugin asset ride the events STATIC mount, which needs
    the staff stack (events_active = events_enabled AND assignments_active)."""
    monkeypatch.setenv("SESSION_SECRET", "s")
    return build(monkeypatch, events=[make_event()], **kw)


def test_preview_page_and_plugin_asset_are_served(monkeypatch):
    """The preview drives the REAL plugin renderer, so the plugin's own asset
    has to be reachable — a copy in the app's frontend would drift from the file
    that actually ships."""
    client, _ = _staff_app(monkeypatch)
    page = client.get("/events/preview.html")
    assert page.status_code == 200
    assert "/events-plugin/cbm-events.js" in page.text
    asset = client.get("/events-plugin/cbm-events.js")
    assert asset.status_code == 200
    assert "CBMEvents.renderCalendar" in asset.text


def test_plugin_asset_absent_when_events_is_off(monkeypatch):
    client, _ = _staff_app(monkeypatch, enabled=False)
    assert client.get("/events-plugin/cbm-events.js").status_code == 404
