"""Read-only probe of the CBM Zoom account — the Phase 0 gate for Events.

Answers the questions that decide whether the Events & Webinars Zoom
integration will work, **without creating, changing or deleting anything**:

1. Do the Server-to-Server OAuth credentials authenticate?
2. Which scopes were actually granted? (Zoom's granular scope names shift
   between API versions, so we ask Zoom rather than guessing.)
3. Can we see the host account and its webinar licence?
4. Can we list webinars for the host?
5. Can we read a past webinar's **participant report**? This is the one most
   likely to be missing — it needs a paid plan and the report scope, and it is
   what automatic attendance depends on (EV-30).

Usage::

    ZOOM_ACCOUNT_ID=... ZOOM_CLIENT_ID=... ZOOM_CLIENT_SECRET=... \
    PYTHONPATH=. uv run python scripts/probe_zoom.py

    # override the host if webinars run under a different account
    ZOOM_HOST_EMAIL=zweb@cbmentors.org ... uv run python scripts/probe_zoom.py

Exits 0 when everything needed for the build is available, 1 otherwise.

**Zoom Meetings** (event hosting plan, `prds/events/event-hosting-plan.md`
§ 7 step 1)::

    # read-only: scopes, the host's meeting capacity and default meeting
    # settings, the meeting list, a past meeting's participant report
    PYTHONPATH=. uv run python scripts/probe_zoom.py --meetings

    # WRITES, only with Doug's yes: one test meeting with registration, one
    # registrant and their personal join link, the registration cancelled,
    # the meeting deleted. Zoom sends the registrant no email.
    PYTHONPATH=. uv run python scripts/probe_zoom.py --meetings \
        --write-test someone@example.org

``ZOOM_HOST_EMAIL`` names the Zoom user the meetings belong to.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import quote

from core.zoom import (
    ZoomAuthError,
    ZoomClient,
    ZoomError,
    parse_zoom_time,
    to_zoom_time,
)

DEFAULT_HOST = "zweb@cbmentors.org"

#: Zoom meeting ``type`` 2: a scheduled, single-occurrence meeting.
MEETING_TYPE_SCHEDULED = 2
#: The test meeting's topic, so a meeting left behind is recognisable.
TEST_TOPIC = "Event hosting probe — safe to delete"

#: Default meeting settings worth reporting for plan § 6 point 4, by the
#: block Zoom keeps them in on GET /users/{id}/settings.
_SETTING_KEYS = {
    "schedule_meeting": ("host_video", "participants_video",
                         "join_before_host", "mute_upon_entry"),
    "in_meeting": ("waiting_room", "screen_sharing", "who_can_share_screen",
                   "chat", "allow_participants_to_rename", "breakout_room"),
    "meeting_security": ("waiting_room", "meeting_password",
                         "require_password_for_scheduled_meeting"),
    "recording": ("cloud_recording", "auto_recording"),
}


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe a Zoom account.")
    parser.add_argument(
        "--meetings", action="store_true",
        help="probe Zoom Meetings instead of Zoom Webinars")
    parser.add_argument(
        "--write-test", metavar="EMAIL", default="",
        help="with --meetings: create, register on, and delete one test meeting")
    args = parser.parse_args(argv)
    if args.write_test and not args.meetings:
        parser.error("--write-test needs --meetings")
    return args


def _scope_lines(scopes: str) -> list[str]:
    return sorted(s for s in scopes.split() if s)


async def probe_meetings(api: Any, host: str) -> list[str]:
    """The read-only Zoom Meetings checks. Returns the blockers found."""
    problems: list[str] = []

    granted = _scope_lines(getattr(api, "scopes", "") or "")
    print(f"       scopes granted ({len(granted)}):")
    for scope in granted:
        print(f"         {scope}")

    # The host: licence type and meeting capacity.
    try:
        user = await api._request("GET", f"/users/{host}")
        licence = {1: "Basic (free)", 2: "Licensed", 3: "On-prem",
                   4: "No feature", 99: "None"}.get(
            user.get("type"), f"type {user.get('type')}")
        print(f"[ok]   host found: {user.get('email')} — {licence}")
        if user.get("type") == 1:
            problems.append(
                "the host is a Basic (free) user — registration and the "
                "participant report need a paid licence")
    except ZoomError as exc:
        print(f"[FAIL] cannot read the host: {exc}")
        problems.append("user:read scope missing, or the host email is wrong")

    try:
        settings = await api._request("GET", f"/users/{host}/settings")
        feature = settings.get("feature") or {}
        capacity = feature.get("meeting_capacity")
        large = feature.get("large_meeting")
        large_cap = feature.get("large_meeting_capacity")
        print(f"[ok]   meeting capacity: {capacity if capacity else 'not reported'}"
              + (f"; large meeting add-on: {large_cap}" if large else ""))
        print(f"       webinar licence on this user: "
              f"{'yes' if feature.get('webinar') else 'no'}")
        print("       default meeting settings (plan § 6 point 4):")
        for block, keys in _SETTING_KEYS.items():
            values = settings.get(block) or {}
            for key in keys:
                if key in values:
                    print(f"         {block}.{key} = {values[key]!r}")
    except ZoomError as exc:
        print(f"[FAIL] cannot read the host's settings: {exc}")
        problems.append("the user settings read was refused (user:read scope)")

    # The meeting list.
    try:
        data = await api._request(
            "GET", f"/users/{host}/meetings",
            params={"page_size": 30, "type": "upcoming"})
        meetings = data.get("meetings", [])
        print(f"[ok]   meeting:read — {len(meetings)} upcoming meeting(s)")
        for meeting in meetings[:5]:
            start = parse_zoom_time(meeting.get("start_time"))
            print(f"       - {meeting.get('id')}  {meeting.get('topic')!r}"
                  f"  {start.isoformat() if start else 'no start time'}")
    except ZoomError as exc:
        print(f"[FAIL] cannot list meetings: {exc}")
        problems.append("meeting list scope missing")

    # A past meeting's participant report — what attendance depends on.
    try:
        past = await api._request(
            "GET", f"/users/{host}/meetings",
            params={"page_size": 5, "type": "previous_meetings"})
        past_list = past.get("meetings", [])
    except ZoomError as exc:
        print(f"[warn] cannot list past meetings: {exc}")
        past_list = []

    if not past_list:
        print("[warn] no past meetings on this host — the participant report\n"
              "       could not be exercised. Hold a short meeting and re-run.")
    else:
        target = past_list[0]
        meeting_id = str(target.get("uuid") or target.get("id"))
        # A UUID that starts with "/" or holds "//" must be double-encoded.
        if meeting_id.startswith("/") or "//" in meeting_id:
            meeting_id = quote(quote(meeting_id, safe=""), safe="")
        try:
            report = await api._request(
                "GET", f"/report/meetings/{meeting_id}/participants",
                params={"page_size": 300})
            participants = report.get("participants", [])
            print(f"[ok]   report:read — {len(participants)} participant(s) in "
                  f"{target.get('topic')!r}")
            if participants:
                sample = participants[0]
                fields = [f for f in ("user_email", "join_time", "leave_time",
                                      "duration", "registrant_id")
                          if sample.get(f) not in (None, "")]
                print(f"       report carries: {', '.join(fields)}")
                if "user_email" not in fields:
                    problems.append(
                        "the meeting report has no participant email — "
                        "attendance cannot be matched to registrations")
        except ZoomError as exc:
            print(f"[FAIL] cannot read the meeting participant report: {exc}")
            problems.append(
                "report scope missing or the plan has no reports — automatic "
                "attendance would not work for Zoom Meetings")
    return problems


async def meeting_write_test(api: Any, host: str, email: str) -> list[str]:
    """One test meeting, end to end, always deleted. Returns blockers."""
    problems: list[str] = []
    start = (datetime.now(timezone.utc) + timedelta(days=7)).replace(
        minute=0, second=0, microsecond=0)
    body = {
        "topic": TEST_TOPIC,
        "type": MEETING_TYPE_SCHEDULED,
        "start_time": to_zoom_time(start),
        "duration": 30,
        "timezone": "America/New_York",
        "settings": {
            "approval_type": 0,          # registration, approved automatically
            "registration_type": 1,      # register once
            "registrants_confirmation_email": False,
            "registrants_email_notification": False,
        },
    }
    try:
        meeting = await api._request(
            "POST", f"/users/{host}/meetings", json_body=body)
    except ZoomError as exc:
        print(f"[FAIL] cannot create a meeting: {exc}")
        return ["meeting create scope missing, or the host may not schedule"]

    meeting_id = str(meeting.get("id"))
    print(f"[ok]   test meeting created: {meeting_id}")
    applied = meeting.get("settings") or {}
    for key in ("approval_type", "registration_type", "waiting_room",
                "mute_upon_entry", "registrants_confirmation_email",
                "registrants_email_notification"):
        print(f"       settings.{key} = {applied.get(key)!r}")
    print(f"       registration_url present: {bool(meeting.get('registration_url'))}")
    try:
        try:
            reg = await api._request(
                "POST", f"/meetings/{meeting_id}/registrants",
                json_body={"email": email, "first_name": "Probe",
                           "last_name": "Registrant"})
            registrant_id = str(reg.get("registrant_id") or "")
            join = str(reg.get("join_url") or "")
            print(f"[ok]   registrant added: id {'present' if registrant_id else 'MISSING'}, "
                  f"personal join link {'present' if join else 'MISSING'}")
            if join and registrant_id and "tk=" in join:
                print("       the join link carries a per-registrant token (tk=)")
            if not join:
                problems.append("a meeting registrant gets no personal join link")
        except ZoomError as exc:
            print(f"[FAIL] cannot register on the meeting: {exc}")
            problems.append("meeting registrant scope missing, or registration "
                            "is not allowed on this plan")
            return problems

        try:
            listed = await api._request(
                "GET", f"/meetings/{meeting_id}/registrants",
                params={"page_size": 30})
            count = len(listed.get("registrants", []))
            print(f"[ok]   registrants listed: {count}")
        except ZoomError as exc:
            print(f"[warn] cannot list registrants: {exc}")

        if registrant_id:
            try:
                await api._request(
                    "PUT", f"/meetings/{meeting_id}/registrants/status",
                    json_body={"action": "cancel",
                               "registrants": [{"id": registrant_id,
                                                "email": email}]},
                    expect_body=False)
                print("[ok]   registration cancelled")
            except ZoomError as exc:
                print(f"[FAIL] cannot cancel the registration: {exc}")
                problems.append("meeting registrant status scope missing")
        return problems
    finally:
        try:
            await api._request(
                "DELETE", f"/meetings/{meeting_id}",
                params={"schedule_for_reminder": "false",
                        "cancel_meeting_reminder": "false"},
                expect_body=False)
            print(f"[ok]   test meeting {meeting_id} deleted")
        except ZoomError as exc:
            print(f"[FAIL] the test meeting {meeting_id} was NOT deleted: {exc}\n"
                  f"       Delete it by hand in Zoom: topic {TEST_TOPIC!r}")
            problems.append("meeting delete scope missing — test meeting left behind")


async def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    account = os.environ.get("ZOOM_ACCOUNT_ID", "")
    client_id = os.environ.get("ZOOM_CLIENT_ID", "")
    secret = os.environ.get("ZOOM_CLIENT_SECRET", "")
    host = os.environ.get("ZOOM_HOST_EMAIL", DEFAULT_HOST)

    if not (account and client_id and secret):
        print("Set ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID and ZOOM_CLIENT_SECRET.\n"
              "Create them at marketplace.zoom.us -> Develop -> Build App ->\n"
              "Server-to-Server OAuth.", file=sys.stderr)
        return 2

    api = ZoomClient(account, client_id, secret)
    problems: list[str] = []
    print(f"Zoom account: {account[:6]}…   host: {host}\n")

    # 1/2. Auth + granted scopes.
    try:
        await api._access_token()
        print("[ok]   credentials authenticate")
    except ZoomAuthError as exc:
        print(f"[FAIL] {exc}")
        return 1

    if args.meetings:
        problems = await probe_meetings(api, host)
        if args.write_test:
            print("\nWrite test — one meeting, created and deleted:")
            problems += await meeting_write_test(api, host, args.write_test)
        print()
        if problems:
            print("BLOCKERS:")
            for problem in problems:
                print(f"  ! {problem}")
            return 1
        print("All Zoom Meetings checks passed.")
        return 0

    # 3. The host account and its licence.
    try:
        user = await api._request("GET", f"/users/{host}")
        licence = {1: "Basic (free)", 2: "Licensed", 3: "On-prem"}.get(
            user.get("type"), f"type {user.get('type')}")
        print(f"[ok]   host found: {user.get('email')} — {licence}")
        features = user.get("feature") or {}
        if features:
            has_webinar = any(
                k.startswith("webinar") and v for k, v in features.items())
            capacity = features.get("webinar_capacity")
            print(f"       webinar licence: {'yes' if has_webinar else 'NOT FOUND'}"
                  + (f", capacity {capacity}" if capacity else ""))
            if not has_webinar:
                problems.append(
                    "the host has no webinar licence — webinars cannot be created")
            elif capacity:
                print(f"       (CEvent.capacity should not exceed {capacity})")
    except ZoomError as exc:
        print(f"[FAIL] cannot read the host account: {exc}")
        problems.append("user:read scope missing, or the host email is wrong")

    # 4. Listing webinars.
    webinars: list[dict] = []
    for kind in ("scheduled", "upcoming"):
        try:
            data = await api._request(
                "GET", f"/users/{host}/webinars",
                params={"page_size": 30, "type": kind},
            )
            webinars = data.get("webinars", [])
            print(f"[ok]   webinar:read — {len(webinars)} {kind} webinar(s)")
            break
        except ZoomError as exc:
            if kind == "upcoming":
                print(f"[FAIL] cannot list webinars: {exc}")
                problems.append("webinar:read scope missing")

    for webinar in webinars[:5]:
        start = parse_zoom_time(webinar.get("start_time"))
        print(f"       - {webinar.get('id')}  {webinar.get('topic')!r}"
              f"  {start.isoformat() if start else 'no start time'}")

    # 5. The participant report — the load-bearing one for attendance.
    try:
        past = await api._request(
            "GET", f"/users/{host}/webinars", params={"page_size": 5, "type": "past"}
        )
        past_list = past.get("webinars", [])
    except ZoomError:
        past_list = []

    if not past_list:
        print("[warn] no past webinars on this host — the attendance report path\n"
              "       could not be exercised. Re-run after the first real webinar.")
    else:
        target = past_list[0]
        try:
            participants = await api.list_participants(str(target.get("id")))
            print(f"[ok]   report:read — {len(participants)} participant(s) in "
                  f"{target.get('topic')!r}")
            if participants:
                sample = participants[0]
                fields = [f for f in ("user_email", "join_time", "leave_time", "duration")
                          if sample.get(f) is not None]
                print(f"       report carries: {', '.join(fields)}")
                if "user_email" not in fields:
                    problems.append(
                        "the report has no participant email — attendance cannot be "
                        "matched to registrations")
        except ZoomError as exc:
            print(f"[FAIL] cannot read the participant report: {exc}")
            problems.append(
                "report:read scope missing or the plan does not include reporting — "
                "automatic attendance (EV-30) will not work")

    print()
    if problems:
        print("BLOCKERS:")
        for problem in problems:
            print(f"  ! {problem}")
        return 1
    print("All checks passed — Zoom is ready for the Events integration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
