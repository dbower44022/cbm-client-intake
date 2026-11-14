"""The old address of the client's survey page (phase 2b, ruling BE23).

    GET /evaluation/{token}   301 to /survey/{token}

Business Evaluation links emailed before phase 2b point here; the page itself
is the survey engine's (``surveys/router.py``). The redirect never reads the
token, so it answers the same for every link, valid or not. The old API
addresses (``/api/evaluation/…``) are gone. While ``BUSINESS_EVALUATION`` is
off this address answers 404 (``core/app.py``).
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["evaluation-public"])


@router.get("/evaluation/{token}", include_in_schema=False)
async def old_address(token: str) -> RedirectResponse:
    return RedirectResponse(f"/survey/{quote(token, safe='')}", status_code=301)
