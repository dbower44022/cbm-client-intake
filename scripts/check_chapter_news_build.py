"""Check the Chapter News build as the application and as a member.

Read-only. As the org-wide API key (the application's credential): both
record types read (HTTP 200, even with no records) and their fields show in
``GET /Metadata``. With ``--as-user``, the same metadata as a real
non-administrator, whose password is typed at the prompt and never stored or
printed (administrators bypass ACL, so their check proves nothing)::

    PYTHONPATH=. uv run python scripts/check_chapter_news_build.py \\
        --env-file ~/.config/cbm-bma/bma.env [--as-user joe.mentor@bma.test]
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from assignments.auth import login_token  # noqa: E402
from core.espo import EspoClient  # noqa: E402
from sandbox.targets import api_connection  # noqa: E402

FIELDS = {
    "CChapterNews": ["name", "summary", "body", "status", "publishAt", "expiresAt",
                     "importance", "audienceTeams", "ctaLabel", "ctaUrl"],
    "CChapterNewsReceipt": ["name", "action", "actedAt", "newsId", "memberId"],
}


async def shape(client: EspoClient, who: str) -> list[str]:
    bad = []
    for entity, fields in FIELDS.items():
        defs = await client.metadata(f"entityDefs.{entity}.fields") or {}
        links = await client.metadata(f"entityDefs.{entity}.links") or {}
        missing = [f for f in fields if f not in defs and f[:-2] not in links]
        print(f"{who}: {entity} metadata {'OK' if not missing else 'MISSING ' + str(missing)}")
        bad += missing
    teams = ((await client.metadata("entityDefs.CChapterNews.fields") or {})
             .get("audienceTeams") or {}).get("options")
    print(f"{who}: audienceTeams offers {teams}")
    return bad


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--as-user", default=None)
    args = parser.parse_args()
    base, key, timeout = api_connection(args.env_file)
    org = EspoClient(base, key, timeout)
    bad = await shape(org, "API key")
    for entity in FIELDS:
        data = await org.list(entity, select="id", max_size=1)
        print(f"API key: GET {entity} -> 200, total {data.get('total')}")
    if args.as_user:
        password = getpass.getpass(f"Password for {args.as_user}: ")
        name, token = await login_token(base, args.as_user, password, timeout)
        member = EspoClient.for_user_token(base, name, token)
        profile = (await member.app_user()).get("user", {})
        print(f"Signed in as {profile.get('userName')} (type={profile.get('type')})")
        bad += await shape(member, args.as_user)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
