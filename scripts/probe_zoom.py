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
"""

from __future__ import annotations

import asyncio
import os
import sys

from core.zoom import ZoomAuthError, ZoomClient, ZoomError, parse_zoom_time

DEFAULT_HOST = "zweb@cbmentors.org"


async def main() -> int:
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
