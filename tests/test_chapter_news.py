"""Chapter News, phase 5 (prds/home-page-plan.md § 6; CHAPTER_NEWS).

The one visibility rule (audience, every status, the publish and expiry
times, a member who joins later), the order, dismiss and acknowledge (a second
click finds the existing receipt), the section that cannot be hidden,
withdraw, the publisher gate, the switches off, the CRM feature detection and
the image gate."""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from forms import info_request, volunteer
from news import rules, service

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def st(days=0.0):
    return rules.stamp(NOW + timedelta(days=days))


def item(i="N1", **kw):
    base = {"id": i, "name": f"Item {i}", "status": rules.PUBLISHED, "publishAt": st(-1),
            "expiresAt": None, "importance": rules.NORMAL, "audienceTeams": [], "body": ""}
    base.update(kw)
    return base


MENTOR = {"userId": "U1", "userName": "joe", "name": "Joe Mentor", "teams": ["Mentor Team"],
          "isAdmin": False}
STAFF = {"userId": "U2", "userName": "kitty", "name": "Kitty Cat",
         "teams": ["Client Administration Team"], "isAdmin": False}
ADMIN = {"userId": "U9", "userName": "doug", "name": "Doug", "teams": [], "isAdmin": True}


# --- the rule -------------------------------------------------------------------

def test_an_empty_audience_is_every_member():
    assert rules.may_see(item(), MENTOR, NOW) and rules.may_see(item(), STAFF, NOW)


def test_a_team_audience_reaches_only_its_teams_administrators_included():
    it = item(audienceTeams=["Mentor Team"])
    assert rules.may_see(it, MENTOR, NOW)
    assert not rules.may_see(it, STAFF, NOW)
    # Being an administrator does not widen an audience (§ 6.1).
    assert not rules.may_see(it, ADMIN, NOW)


@pytest.mark.parametrize("status, seen", [(rules.DRAFT, False), (rules.PUBLISHED, True),
                                          (rules.WITHDRAWN, False)])
def test_only_published_items_are_seen(status, seen):
    assert rules.may_see(item(status=status), MENTOR, NOW) is seen


def test_an_item_waits_for_its_publish_time():
    assert not rules.may_see(item(publishAt=st(1)), MENTOR, NOW)
    assert rules.may_see(item(publishAt=st(-0.01)), MENTOR, NOW)
    assert rules.may_see(item(publishAt=None), MENTOR, NOW)


def test_an_expired_item_leaves_the_section_and_stays_in_past_news():
    it = item(expiresAt=st(-0.5))
    assert rules.may_see(it, MENTOR, NOW) and not rules.is_live(it, MENTOR, NOW)
    assert rules.unread([it], {}, MENTOR, NOW) == []
    assert [i["id"] for i, _ in rules.past([it], {}, MENTOR, NOW)] == ["N1"]


def test_a_member_who_joins_later_sees_the_teams_live_items():
    it = item(audienceTeams=["Client Administration Team"], publishAt=st(-30))
    assert not rules.may_see(it, MENTOR, NOW)
    joined = {**MENTOR, "teams": ["Mentor Team", "Client Administration Team"]}
    assert rules.unread([it], {}, joined, NOW)[0]["id"] == "N1"
    # ...but not one that expired before they joined.
    old = item("N2", audienceTeams=["Client Administration Team"], expiresAt=st(-1))
    assert rules.unread([old], {}, joined, NOW) == []


def test_the_order_is_acknowledge_then_pinned_then_newest():
    items = [item("A", publishAt=st(-1)), item("B", publishAt=st(-3), importance=rules.PINNED),
             item("C", publishAt=st(-5), importance=rules.ACKNOWLEDGE),
             item("D", publishAt=st(-0.5)), item("E", publishAt=st(-2), importance=rules.PINNED)]
    assert [i["id"] for i in rules.unread(items, {}, MENTOR, NOW)] == ["C", "E", "B", "D", "A"]


def test_a_receipt_takes_an_item_off_the_section():
    items = [item("A"), item("B")]
    left = rules.unread(items, {"A": {"action": rules.DISMISSED}}, MENTOR, NOW)
    assert [i["id"] for i in left] == ["B"]


def test_past_news_says_how_each_item_stands():
    items = [item("A", publishAt=st(-1)), item("B", publishAt=st(-2)),
             item("C", publishAt=st(-3), importance=rules.ACKNOWLEDGE, expiresAt=st(-0.1)),
             item("D", publishAt=st(-4), expiresAt=st(-0.1)),
             item("E", publishAt=st(-5), importance=rules.ACKNOWLEDGE),
             item("W", status=rules.WITHDRAWN)]
    receipts = {"A": {"action": rules.DISMISSED}, "E": {"action": rules.ACKNOWLEDGED}}
    got = [(i["id"], s) for i, s in rules.past(items, receipts, MENTOR, NOW)]
    assert got == [("A", "Dismissed"), ("B", "Unread"), ("C", "Not acknowledged"),
                   ("D", "Expired"), ("E", "Acknowledged")]


def test_the_section_cannot_be_hidden_while_an_item_to_acknowledge_waits():
    ack = item("A", importance=rules.ACKNOWLEDGE)
    assert rules.blocks_hiding([ack], {}, MENTOR, NOW)
    assert not rules.blocks_hiding([ack], {"A": {"action": rules.ACKNOWLEDGED}}, MENTOR, NOW)
    # An expired item to acknowledge stops prompting (decision 7).
    assert not rules.blocks_hiding([item("A", importance=rules.ACKNOWLEDGE, expiresAt=st(-1))],
                                   {}, MENTOR, NOW)
    assert not rules.blocks_hiding([item("A", importance=rules.PINNED)], {}, MENTOR, NOW)


# --- the publisher's input ---------------------------------------------------------

TEAMS = ["Client Administration Team", "Mentor Team"]


def test_a_published_item_with_no_publish_time_goes_out_now():
    f = service.clean_item({"title": "T", "status": "Published"}, TEAMS)
    assert f["publishAt"] and f["status"] == "Published"
    assert service.clean_item({"title": "T"}, TEAMS)["publishAt"] is None


@pytest.mark.parametrize("data, words", [
    ({"title": ""}, "title"),
    ({"title": "T", "importance": "Urgent"}, "Normal, Pinned"),
    ({"title": "T", "status": "Withdrawn"}, "Withdraw"),
    ({"title": "T", "audienceTeams": ["Nobody Team"]}, "Nobody Team"),
    ({"title": "T", "ctaLabel": "Go"}, "both"),
    ({"title": "T", "ctaLabel": "Go", "ctaUrl": "javascript:alert(1)"}, "https://"),
    ({"title": "T", "publishAt": "2026-11-20 10:00:00", "expiresAt": "2026-11-20 09:00:00"}, "after"),
])
def test_bad_input_is_refused_in_words(data, words):
    with pytest.raises(service.NewsError) as exc:
        service.clean_item(data, TEAMS)
    assert words in str(exc.value)


def test_a_member_gets_a_safe_body_with_images_through_the_proxy():
    it = item(body='<p onclick="x()">Hi<script>alert(1)</script>'
                   '<img src="?entryPoint=attachment&amp;id=att1"></p>')
    html = service.member_body(it)
    assert "script" not in html and "onclick" not in html
    assert 'src="/api/portal/home/news/N1/images/att1"' in html
    assert service.image_ids(it["body"]) == {"att1"}


# --- a CRM in memory ------------------------------------------------------------------

class FakeCrm:
    def __init__(self, built=True):
        self.built = built
        self.rows = {service.NEWS: {}, service.RECEIPT: {}}
        self.ids = itertools.count(1)
        self.creates = []

    async def metadata(self, key):
        if not self.built:
            return None
        if key == f"entityDefs.{service.NEWS}.fields":
            return {"audienceTeams": {"type": "multiEnum", "options": TEAMS}}
        if key == f"entityDefs.{service.RECEIPT}.fields":
            return {"action": {"type": "enum"}}
        return None

    async def list(self, entity, select=None, where=None, order_by=None, order="desc",
                   max_size=20, offset=0, **kw):
        assert max_size <= 200
        rows = list(self.rows[entity].values())
        for w in where or []:
            rows = [r for r in rows if r.get(w["attribute"]) == w["value"]]
        return {"list": [dict(r) for r in rows[offset:offset + max_size]], "total": len(rows)}

    async def get(self, entity, rid):
        return dict(self.rows[entity][rid])

    async def create(self, entity, payload):
        rid = f"R{next(self.ids)}"
        self.rows[entity][rid] = {"id": rid, **payload}
        self.creates.append((entity, payload))
        return dict(self.rows[entity][rid])

    async def update(self, entity, rid, payload):
        self.rows[entity][rid].update(payload)
        return dict(self.rows[entity][rid])

    async def download_attachment(self, aid):
        return b"PNG", "image/png"


@pytest.fixture(autouse=True)
def _fresh():
    get_settings.cache_clear()
    service.invalidate()
    service._available.update(ok=None, at=0.0)
    yield
    get_settings.cache_clear()
    service.invalidate()
    service._available.update(ok=None, at=0.0)


@pytest.mark.asyncio
async def test_a_second_click_finds_the_existing_receipt():
    crm = FakeCrm()
    it = item()
    first, made = await service.record_receipt(crm, it, MENTOR, rules.DISMISSED, NOW)
    again, made_again = await service.record_receipt(crm, it, MENTOR, rules.DISMISSED, NOW)
    assert made and not made_again and again["id"] == first["id"]
    assert len(crm.rows[service.RECEIPT]) == 1
    row = next(iter(crm.rows[service.RECEIPT].values()))
    assert row["memberId"] == "U1" and row["newsId"] == "N1" and row["action"] == "Dismissed"


@pytest.mark.asyncio
async def test_the_feature_stays_dark_until_both_record_types_exist():
    crm = FakeCrm(built=False)
    assert await service.available(crm) is False
    crm.built = True
    assert await service.available(crm) is False          # a no is believed a while
    service._available.update(at=0.0 - service.ABSENT_SECONDS - 1)
    assert await service.available(crm) is True


# --- the routes ---------------------------------------------------------------------

def _app(monkeypatch, crm, **env):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    env = {"HOME_V2": "true", "CHAPTER_NEWS": "true", **env}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    monkeypatch.setattr(service, "key_client", lambda settings: crm)
    return create_app([info_request.SPEC, volunteer.SPEC])


def _login(monkeypatch, client, user):
    async def fake_auth(settings, username, password, *, gate=True, **kwargs):
        return {"token": "tok", "roles": [], **user}

    async def fake_refresh(settings, session_user):
        return dict(session_user)

    monkeypatch.setattr("portal.router.authenticate", fake_auth)
    monkeypatch.setattr("portal.router.refresh_membership", fake_refresh)
    return client.post("/api/portal/login", json={"username": "x", "password": "x"}).json()


def _seed(crm, *items):
    for it in items:
        crm.rows[service.NEWS][it["id"]] = {**it, "publishAt": rules.stamp(
            datetime.now(timezone.utc) - timedelta(days=1)) if it.get("publishAt") else None}


def test_the_switches_off_hide_every_member_route(monkeypatch):
    crm = FakeCrm()
    for env in ({"CHAPTER_NEWS": "false"}, {"HOME_V2": "false"}):
        with TestClient(_app(monkeypatch, crm, **env)) as c:
            data = _login(monkeypatch, c, MENTOR)
            assert "news" not in (data.get("home") or {}).get("sections", [])
            assert c.get("/api/portal/home/news").status_code == 404
            assert c.get("/api/portal/home/news/past").status_code == 404


def test_news_is_the_first_section_and_the_tile_is_for_publishers(monkeypatch):
    crm = FakeCrm()
    with TestClient(_app(monkeypatch, crm)) as c:
        data = _login(monkeypatch, c, MENTOR)
        assert data["home"]["sections"][0] == "news"
        assert "Chapter News" not in [a["title"] for a in data["apps"]]
        assert c.get("/news/api/session").status_code == 403
        pub = _login(monkeypatch, c, {**STAFF, "teams": ["System Management Team"]})
        assert "Chapter News" in [a["title"] for a in pub["apps"]]
        assert c.get("/news/api/session").json()["built"] is True
        _login(monkeypatch, c, ADMIN)
        assert c.get("/news/api/session").status_code == 200


def test_where_the_crm_has_no_chapter_news_the_section_says_so(monkeypatch):
    crm = FakeCrm(built=False)
    with TestClient(_app(monkeypatch, crm)) as c:
        _login(monkeypatch, c, MENTOR)
        assert c.get("/api/portal/home/news").json() == {
            "available": False, "items": [], "blocksHiding": False}
        _login(monkeypatch, c, ADMIN)
        assert c.get("/news/api/session").json()["built"] is False
        assert c.get("/news/api/items").status_code == 503


def test_a_member_dismisses_acknowledges_and_reads_past_news(monkeypatch):
    crm = FakeCrm()
    _seed(crm, item("A", publishAt=True, importance=rules.ACKNOWLEDGE),
          item("B", publishAt=True), item("S", publishAt=True, audienceTeams=["Client Administration Team"]),
          item("W", publishAt=True, status=rules.WITHDRAWN))
    with TestClient(_app(monkeypatch, crm)) as c:
        _login(monkeypatch, c, MENTOR)
        got = c.get("/api/portal/home/news").json()
        assert [i["id"] for i in got["items"]] == ["A", "B"] and got["blocksHiding"] is True
        # The item to acknowledge has no Dismiss, and the other no acknowledge.
        assert c.post("/api/portal/home/news/A/dismiss").status_code == 400
        assert c.post("/api/portal/home/news/B/acknowledge").status_code == 400
        assert c.post("/api/portal/home/news/A/acknowledge").json()["created"] is True
        assert c.post("/api/portal/home/news/A/acknowledge").json()["created"] is False
        assert c.post("/api/portal/home/news/B/dismiss").json()["action"] == "Dismissed"
        got = c.get("/api/portal/home/news").json()
        assert got["items"] == [] and got["blocksHiding"] is False
        past = c.get("/api/portal/home/news/past").json()["items"]
        assert {i["id"]: i["state"] for i in past} == {"A": "Acknowledged", "B": "Dismissed"}
        # Outside the audience, withdrawn and unknown read the same.
        for nid in ("S", "W", "nope"):
            r = c.post(f"/api/portal/home/news/{nid}/dismiss")
            assert r.status_code == 404 and r.json()["detail"] == "That news item was not found."


def test_an_image_is_served_only_from_an_item_the_member_may_see(monkeypatch):
    crm = FakeCrm()
    body = '<img src="?entryPoint=attachment&amp;id=att1">'
    _seed(crm, item("A", publishAt=True, body=body),
          item("S", publishAt=True, body=body, audienceTeams=["Client Administration Team"]))
    with TestClient(_app(monkeypatch, crm)) as c:
        _login(monkeypatch, c, MENTOR)
        assert c.get("/api/portal/home/news/A/images/att1").status_code == 200
        assert c.get("/api/portal/home/news/A/images/other").status_code == 404
        assert c.get("/api/portal/home/news/S/images/att1").status_code == 404


def test_a_publisher_publishes_and_withdraws_and_each_is_logged(monkeypatch):
    crm = FakeCrm()
    logged = []

    async def fake_log(**kw):
        logged.append(kw)
        return True

    monkeypatch.setattr("core.action_log.log_action", fake_log)
    with TestClient(_app(monkeypatch, crm)) as c:
        _login(monkeypatch, c, ADMIN)
        r = c.post("/news/api/items", json={"title": "Elections", "status": "Published",
                                            "summary": "Vote", "audienceTeams": ["Mentor Team"]})
        assert r.status_code == 200, r.text
        nid = r.json()["id"]
        assert c.post("/news/api/items", json={"title": ""}).status_code == 400
        _login(monkeypatch, c, MENTOR)
        assert [i["id"] for i in c.get("/api/portal/home/news").json()["items"]] == [nid]
        _login(monkeypatch, c, ADMIN)
        assert c.post(f"/news/api/items/{nid}/withdraw").json()["status"] == "Withdrawn"
        _login(monkeypatch, c, MENTOR)
        # Gone at once in this process: the section and past news alike.
        assert c.get("/api/portal/home/news").json()["items"] == []
        assert c.get("/api/portal/home/news/past").json()["items"] == []
    assert [k["action"] for k in logged] == ["Published", "Withdrew"]
    assert all(k["actor_name"] == "Doug" and k["parent_type"] == "CChapterNews" for k in logged)


def test_the_publisher_image_proxy_serves_only_news_images(monkeypatch):
    crm = FakeCrm()
    _seed(crm, item("A", publishAt=True, body='<img src="?entryPoint=attachment&amp;id=att1">'))
    with TestClient(_app(monkeypatch, crm)) as c:
        _login(monkeypatch, c, ADMIN)
        assert c.get("/news/api/attachments/att1").status_code == 200
        assert c.get("/news/api/attachments/someone-elses").status_code == 404


# --- the pages ------------------------------------------------------------------------

def test_the_pages_load_their_files_in_order():
    page = (ROOT / "news/frontend/index.html").read_text()
    assert page.index("/shared/busy.js") < page.index("/shared/textsize.js") < page.index("app.js")
    for need in ("/shared/richtext.js", "/shared/datetime.js", "/shared/news.js", "/shared/grid.js"):
        assert need in page
    home = (ROOT / "portal/frontend/index.html").read_text()
    assert home.index("/shared/news.js") < home.index("/portal/home.js")
    js = (ROOT / "portal/frontend/home.js").read_text()
    # The Hide button stays and explains itself while an item waits (§ 4.3).
    assert "can't be hidden while an item asks you to confirm" in js
