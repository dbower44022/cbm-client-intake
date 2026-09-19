#!/usr/bin/env python3
"""Render a DigitalOcean App Platform spec for a chapter from its values file
plus its secrets env file. A measurement for Phase 3 (spec generator): this is
the whole of what a generator has to do. Output is plaintext-secret YAML that
must never be committed; feed it straight to `doctl apps create --spec`.

    render_spec.py VALUES ENV OUT

Nothing chapter- or rehearsal-specific is written into the spec by this script
(fixed 2026-09-19; it used to hard-code three of the trial chapter's values):

* no ENV_LABEL — the footer label is derived from the CRM address, which is right
  for a real chapter;
* ALLOWED_ORIGINS is the origin of the chapter's application address, never
  localhost, and is left out when that address is not known yet;
* every component follows the ``release`` branch unless the values file names
  another under ``deploy.branch``. The development branch ``main`` is refused
  unless ``deploy.allow_development_branch`` is true, because a chapter on
  ``main`` takes untested code straight to its live system.

The database is created as a development database, which is all a spec can
create. Convert it to a managed database straight after creation (deployment
guide step 11.4) — a development database takes no backups.
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit

import yaml

REPO_SLUG = "dbower44022/cbm-client-intake"
RELEASE_BRANCH = "release"
DEVELOPMENT_BRANCH = "main"


def read_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        if raw.strip() and not raw.startswith("#") and "=" in raw:
            k, v = raw.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def ev(key: str, value, secret: bool = False, scope: str = "RUN_TIME") -> dict:
    d = {"key": key, "scope": scope, "value": str(value)}
    if secret:
        d["type"] = "SECRET"
    return d


def origin(url: str) -> str:
    """The scheme and host of an address, with no path: what ALLOWED_ORIGINS holds."""
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"not an absolute address: {url!r}")
    return f"{parts.scheme}://{parts.netloc}"


def deploy_branch(values: dict) -> str:
    deploy = values.get("deploy") or {}
    branch = deploy.get("branch") or RELEASE_BRANCH
    if branch == DEVELOPMENT_BRANCH and not deploy.get("allow_development_branch"):
        raise ValueError(
            f"deploy.branch is {DEVELOPMENT_BRANCH!r}: a chapter must follow "
            f"{RELEASE_BRANCH!r}. Set deploy.allow_development_branch: true only "
            f"for the one soak copy."
        )
    return branch


def build_spec(values: dict, env: dict[str, str]) -> dict:
    """The App Platform spec for one chapter. ``env`` must already hold the
    minted secrets; see main() for SESSION_SECRET / APP_ENCRYPTION_KEY."""
    missing = [k for k in ("ESPO_API_KEY", "ESPO_PROVISION_USERNAME", "ESPO_PROVISION_PASSWORD",
                           "SESSION_SECRET", "APP_ENCRYPTION_KEY") if k not in env]
    if missing:
        raise ValueError(f"secrets not yet minted: {missing}")
    slug = values["chapter"]["slug"]
    db = f"{slug}-db"
    f = values["flags"]
    w = values["web"]
    c = values["crm"]
    common = [
        ev("ESPO_DRY_RUN", str(f["espo_dry_run"]).lower()),
        ev("ESPO_BASE_URL", c["base_url"]),
        ev("ESPO_API_KEY", env["ESPO_API_KEY"], secret=True),
        ev("DATABASE_URL", f"${{{db}.DATABASE_URL}}"),
        ev("ASYNC_DELIVERY", str(f["async_delivery"]).lower()),
        ev("ANALYTICS_ENABLED", str(f["analytics_enabled"]).lower()),
        ev("ORGANIZATION_NAME", values["chapter"]["name"]),
        ev("GMAIL_SYNC", "false"), ev("GCAL_EVENTS", "false"), ev("GDRIVE_DOCS", "false"),
    ]
    web_only = [
        ev("SESSION_SECRET", env["SESSION_SECRET"], secret=True),
        ev("APP_ENCRYPTION_KEY", env["APP_ENCRYPTION_KEY"], secret=True),
        ev("SESSION_COOKIE_SECURE", "true"),
        ev("SETUP_ENABLED", str(f["setup_enabled"]).lower()),
        ev("EVENTS_ENABLED", str(f["events_enabled"]).lower()),
        ev("EVENTS_PUBLIC_API", str(f["events_public_api"]).lower()),
        ev("RECORD_QUICK_ADD", str(f["record_quick_add"]).lower()),
        ev("MENTOR_PROVISION_USERS", str(f["mentor_provision_users"]).lower()),
        ev("GOOGLE_DIRECTORY_CHECK", "false"),
        ev("ESPO_PROVISION_USERNAME", env["ESPO_PROVISION_USERNAME"]),
        ev("ESPO_PROVISION_PASSWORD", env["ESPO_PROVISION_PASSWORD"], secret=True),
        ev("CRM_CONFIG_REFRESH_SECONDS", "300"),
        ev("POLICY_CLIENT_CONDUCT_URL", w["policy_client_conduct_url"]),
        ev("POLICY_MENTOR_ETHICS_URL", w["policy_mentor_ethics_url"]),
        ev("POLICY_TERMS_URL", w["policy_terms_url"]),
        ev("POLICY_PRIVACY_URL", w["policy_privacy_url"]),
    ]
    if w.get("events_public_base_url"):
        web_only.append(ev("EVENTS_PUBLIC_BASE_URL", w["events_public_base_url"]))
    if w.get("app_base_url"):
        web_only.append(ev("APP_BASE_URL", w["app_base_url"]))
        web_only.append(ev("ALLOWED_ORIGINS", origin(w["app_base_url"])))
    if w.get("docs_site_url"):
        web_only.append(ev("DOCS_SITE_URL", w["docs_site_url"]))
    if env.get("RELEASE_TAG"):
        web_only.append(ev("RELEASE_TAG", env["RELEASE_TAG"], scope="RUN_AND_BUILD_TIME"))
    branch = deploy_branch(values)
    gh = {"repo": REPO_SLUG, "branch": branch, "deploy_on_push": bool(f["deploy_on_push"])}
    return {
        "name": f"{slug}-intake",
        "region": "nyc",
        "databases": [{"name": db, "engine": "PG", "version": "16", "production": False}],
        "jobs": [{"name": "migrate", "kind": "PRE_DEPLOY", "dockerfile_path": "Dockerfile",
                  "github": {"repo": REPO_SLUG, "branch": branch},
                  "instance_count": 1, "instance_size_slug": "apps-s-1vcpu-0.5gb",
                  "run_command": ".venv/bin/alembic upgrade head",
                  "envs": [ev("DATABASE_URL", f"${{{db}.DATABASE_URL}}")]}],
        "services": [{"name": "web", "dockerfile_path": "Dockerfile", "github": gh,
                      "http_port": 8080, "instance_count": 1, "instance_size_slug": "basic-xxs",
                      "health_check": {"http_path": "/healthz"}, "envs": common + web_only}],
        "workers": [{"name": "delivery-worker", "dockerfile_path": "Dockerfile", "github": gh,
                     "instance_count": 1, "instance_size_slug": "basic-xxs",
                     "run_command": ".venv/bin/python -m worker", "envs": common}],
        "ingress": {"rules": [{"component": {"name": "web"}, "match": {"path": {"prefix": "/"}}}]},
    }


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    values_path, env_path, out_path = (Path(a) for a in argv[1:])
    values = yaml.safe_load(values_path.read_text())
    env = read_env(env_path)
    for k, n in (("SESSION_SECRET", 48), ("APP_ENCRYPTION_KEY", 32)):
        if k not in env:  # mint once and persist — rotating APP_ENCRYPTION_KEY later would be data loss
            env[k] = secrets.token_urlsafe(n)
            with open(env_path, "a") as fh:
                fh.write(f"{k}={env[k]}\n")
    try:
        spec = build_spec(values, env)
    except (ValueError, KeyError) as exc:
        print(f"cannot render: {exc}", file=sys.stderr)
        return 2
    out_path.write_text(yaml.safe_dump(spec, sort_keys=False))
    web = spec["services"][0]
    print("wrote", out_path, "following branch", web["github"]["branch"], "with",
          len(spec["workers"][0]["envs"]), "shared +",
          len(web["envs"]) - len(spec["workers"][0]["envs"]), "web-only env vars")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
