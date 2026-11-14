"""The Zoom Meetings probe (event hosting plan § 7 step 1).

The write test touches a real Zoom account, so the one property that must
hold whatever Zoom answers is checked here: the test meeting is always
deleted, and Zoom is asked to send the registrant nothing.
"""

from __future__ import annotations

import pytest

from core.zoom import ZoomError
from scripts import probe_zoom


class FakeApi:
    def __init__(self, fail_on: str = ""):
        self.calls: list[tuple[str, str, dict]] = []
        self.fail_on = fail_on
        self.scopes = "meeting:write:meeting:admin user:read:user:admin"

    async def _request(self, method, path, *, params=None, json_body=None,
                       expect_body=True):
        self.calls.append((method, path, json_body or params or {}))
        if self.fail_on and self.fail_on in f"{method} {path}":
            raise ZoomError("HTTP 400 refused", status_code=400)
        if method == "POST" and path.endswith("/meetings"):
            return {"id": 123, "settings": json_body["settings"],
                    "registration_url": "https://zoom.us/meeting/register/x"}
        if method == "POST" and path.endswith("/registrants"):
            return {"registrant_id": "r1",
                    "join_url": "https://zoom.us/w/123?tk=abc"}
        if method == "GET" and path.endswith("/registrants"):
            return {"registrants": [{"id": "r1"}]}
        return {}


def _deleted(api):
    return [c for c in api.calls if c[0] == "DELETE" and c[1] == "/meetings/123"]


@pytest.mark.asyncio
async def test_write_test_runs_the_whole_cycle_and_deletes():
    api = FakeApi()
    problems = await probe_zoom.meeting_write_test(api, "h@x.org", "p@x.org")
    assert problems == []
    create = api.calls[0][2]
    assert create["settings"]["approval_type"] == 0
    assert create["settings"]["registrants_confirmation_email"] is False
    assert create["settings"]["registrants_email_notification"] is False
    assert any(c[0] == "PUT" and c[2]["action"] == "cancel" for c in api.calls)
    delete = _deleted(api)
    assert delete and delete[0][2]["cancel_meeting_reminder"] == "false"


@pytest.mark.asyncio
async def test_meeting_is_deleted_even_when_registration_fails():
    api = FakeApi(fail_on="POST /meetings/123/registrants")
    problems = await probe_zoom.meeting_write_test(api, "h@x.org", "p@x.org")
    assert problems and "registrant" in problems[0]
    assert _deleted(api)


@pytest.mark.asyncio
async def test_a_failed_create_deletes_nothing():
    api = FakeApi(fail_on="POST /users/h@x.org/meetings")
    problems = await probe_zoom.meeting_write_test(api, "h@x.org", "p@x.org")
    assert problems
    assert not [c for c in api.calls if c[0] == "DELETE"]


def test_write_test_needs_meetings():
    with pytest.raises(SystemExit):
        probe_zoom._parse_args(["--write-test", "p@x.org"])


@pytest.mark.asyncio
async def test_read_only_probe_never_writes():
    api = FakeApi()
    await probe_zoom.probe_meetings(api, "h@x.org")
    assert {c[0] for c in api.calls} == {"GET"}
