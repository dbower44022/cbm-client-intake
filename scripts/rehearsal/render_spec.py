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

Every chapter setting on the form reaches the spec (fixed 2026-09-23, before the
first real chapter). The script used to hard-code the Google switches off and
leave out the chapter's website, mentor email domain, internal domains, Google,
Drive, alert and Zoom settings, so a chapter silently ran on Cleveland's
defaults for all of them — and setting them at ``/setup`` afterwards does not
help the worker, which decides at start-up from its environment whether to poll
the mailbox and sync mail. They are environment variables here for that reason.

The Google key is read from the file named by ``GOOGLE_SERVICE_ACCOUNT_KEY_FILE``
in the secrets file, never pasted into it: the build steps load that file with
``env $(grep … | xargs)``, which a multi-line JSON key would break.

``APP_ENCRYPTION_KEY`` is minted as a real Fernet key and checked. It used to be
``secrets.token_urlsafe(32)``, which the application rejects, so ``/setup``
refused to store any secret at all.

The database is created as a development database, which is all a spec can
create. Convert it to a managed database straight after creation (deployment
guide step 11.4) — a development database takes no backups.
"""
from __future__ import annotations

import json
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from cryptography.fernet import Fernet

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


# What a form field holds when the chapter has nothing to put there yet. The
# guide tells chapters to write "none yet" rather than leave a field blank, so
# that is treated as absent — it must never reach the application as an address.
_NOT_YET = {"", "none yet", "none", "n/a", "tbd"}


def given(value) -> str:
    """The value as a string, or "" when the form says there is none yet."""
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in _NOT_YET else text


def flag(flags: dict, name: str) -> str:
    """A switch from the form as the environment spells it. An absent switch is off."""
    return str(bool(flags.get(name))).lower()


def check_encryption_key(key: str) -> None:
    try:
        Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "APP_ENCRYPTION_KEY in the secrets file is not a valid key "
            f"({exc}). If nothing has been stored encrypted yet, delete that "
            "line and run again to mint a new one."
        ) from exc


def google_key(env: dict[str, str]) -> str:
    """The service-account key, compacted to one line, or "" when none is named."""
    path = given(env.get("GOOGLE_SERVICE_ACCOUNT_KEY_FILE"))
    if not path:
        return ""
    key = json.loads(Path(path).expanduser().read_text())
    if key.get("type") != "service_account" or "private_key" not in key:
        raise ValueError(f"{path} is not a service-account key file")
    return json.dumps(key, separators=(",", ":"))


GOOGLE_FLAGS = ("gmail_sync", "gcal_events", "gdrive_docs", "google_directory_check",
                "google_create_mailbox")


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
    owed = [k for k, v in values["flags"].items() if v == "owed"]
    if owed:
        raise ValueError(
            f"flags {owed} are marked not known yet (owed) in the values file. Answer "
            "them on the chapter information page and write the values file again "
            "(deployment guide step 8.10)."
        )
    missing = [k for k in ("ESPO_API_KEY", "ESPO_PROVISION_USERNAME", "ESPO_PROVISION_PASSWORD",
                           "SESSION_SECRET", "APP_ENCRYPTION_KEY") if k not in env]
    if missing:
        raise ValueError(f"secrets not yet minted: {missing}")
    check_encryption_key(env["APP_ENCRYPTION_KEY"])
    slug = values["chapter"]["slug"]
    db = f"{slug}-db"
    f = values["flags"]
    w = values["web"]
    c = values["crm"]
    g = values.get("google") or {}
    z = values.get("zoom") or {}

    gkey = google_key(env)
    wanted = [n for n in GOOGLE_FLAGS if f.get(n)]
    if wanted and not gkey:
        raise ValueError(
            f"flags {wanted} are on but GOOGLE_SERVICE_ACCOUNT_KEY_FILE is not in the "
            "secrets file (stage 10). Add it, or switch those flags off and render again "
            "once stage 10 is done."
        )
    if f.get("gdrive_docs") and not given(g.get("shared_drive_id")):
        raise ValueError("flags.gdrive_docs is on but google.shared_drive_id is empty (step 10.5)")
    if f.get("google_create_mailbox") and not f.get("google_directory_check"):
        raise ValueError("flags.google_create_mailbox needs flags.google_directory_check on")

    # Internal mail: the staff domain plus the mentors' domain when it differs.
    domains = [d for d in (given(g.get("primary_domain")), given(g.get("mentor_email_domain"))) if d]
    internal = ",".join(dict.fromkeys(domains))

    common = [
        ev("ESPO_DRY_RUN", str(f["espo_dry_run"]).lower()),
        ev("ESPO_BASE_URL", c["base_url"]),
        ev("ESPO_API_KEY", env["ESPO_API_KEY"], secret=True),
        ev("DATABASE_URL", f"${{{db}.DATABASE_URL}}"),
        # Both processes read settings stored encrypted at /setup, so both need the key.
        ev("APP_ENCRYPTION_KEY", env["APP_ENCRYPTION_KEY"], secret=True),
        ev("ASYNC_DELIVERY", str(f["async_delivery"]).lower()),
        ev("ANALYTICS_ENABLED", str(f["analytics_enabled"]).lower()),
        ev("ORGANIZATION_NAME", values["chapter"]["name"]),
        ev("GMAIL_SYNC", flag(f, "gmail_sync")),
        ev("GDRIVE_DOCS", flag(f, "gdrive_docs")),
        ev("ZOOM_EVENTS", flag(f, "zoom_events")),
    ]
    web_only = [
        ev("SESSION_SECRET", env["SESSION_SECRET"], secret=True),
        ev("SESSION_COOKIE_SECURE", "true"),
        ev("SETUP_ENABLED", str(f["setup_enabled"]).lower()),
        ev("EVENTS_ENABLED", str(f["events_enabled"]).lower()),
        ev("EVENTS_PUBLIC_API", str(f["events_public_api"]).lower()),
        ev("RECORD_QUICK_ADD", str(f["record_quick_add"]).lower()),
        ev("MENTOR_PROVISION_USERS", str(f["mentor_provision_users"]).lower()),
        ev("GCAL_EVENTS", flag(f, "gcal_events")),
        ev("GOOGLE_DIRECTORY_CHECK", flag(f, "google_directory_check")),
        ev("GOOGLE_CREATE_MAILBOX", flag(f, "google_create_mailbox")),
        ev("ESPO_PROVISION_USERNAME", env["ESPO_PROVISION_USERNAME"]),
        ev("ESPO_PROVISION_PASSWORD", env["ESPO_PROVISION_PASSWORD"], secret=True),
        ev("CRM_CONFIG_REFRESH_SECONDS", "300"),
        ev("POLICY_CLIENT_CONDUCT_URL", w["policy_client_conduct_url"]),
        ev("POLICY_MENTOR_ETHICS_URL", w["policy_mentor_ethics_url"]),
        ev("POLICY_TERMS_URL", w["policy_terms_url"]),
        ev("POLICY_PRIVACY_URL", w["policy_privacy_url"]),
    ]

    def add(target: list, key: str, value, secret: bool = False) -> None:
        if given(value):
            target.append(ev(key, given(value), secret=secret))

    # Settings both processes use: mail, Drive, alerts and the Zoom account.
    add(common, "GOOGLE_SERVICE_ACCOUNT_JSON", gkey, secret=True)
    add(common, "OPS_MAILBOX", g.get("ops_mailbox"))
    add(common, "ALERT_EMAIL_FROM", g.get("alert_email_from"))
    add(common, "ALERT_EMAIL_TO", g.get("alert_email_to"))
    add(common, "COMMS_INTERNAL_DOMAINS", internal)
    add(common, "MENTOR_EMAIL_DOMAIN", g.get("mentor_email_domain"))
    add(common, "GOOGLE_DELEGATED_ADMIN", g.get("delegated_admin"))
    add(common, "GOOGLE_MEMBERS_GROUP", g.get("members_group"))
    add(common, "GDRIVE_SHARED_DRIVE_ID", g.get("shared_drive_id"))
    add(common, "GDRIVE_IDENTITY", f.get("gdrive_identity"))
    add(common, "ZOOM_ACCOUNT_ID", z.get("account_id"))
    add(common, "ZOOM_CLIENT_ID", z.get("client_id"))
    add(common, "ZOOM_CLIENT_SECRET", env.get("ZOOM_CLIENT_SECRET"), secret=True)
    add(common, "ZOOM_HOST_EMAIL", g.get("zoom_host_email"))
    if given(w.get("app_base_url")):
        common.append(ev("APP_BASE_URL", given(w["app_base_url"])))
        web_only.append(ev("ALLOWED_ORIGINS", origin(given(w["app_base_url"]))))
    # Settings only the web process uses: the public pages and the portal.
    add(web_only, "ORGANIZATION_WEBSITE_URL", w.get("website_base_url"))
    add(web_only, "CHAPTER_TOKENS_URL", w.get("chapter_tokens_url"))
    add(web_only, "DOCS_SITE_URL", w.get("docs_site_url"))
    add(web_only, "EVENTS_PUBLIC_BASE_URL", w.get("events_public_base_url"))
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
    minters = (("SESSION_SECRET", lambda: secrets.token_urlsafe(48)),
               ("APP_ENCRYPTION_KEY", lambda: Fernet.generate_key().decode()))
    for k, mint in minters:
        if k not in env:  # mint once and persist — rotating APP_ENCRYPTION_KEY later would be data loss
            env[k] = mint()
            with open(env_path, "a") as fh:
                fh.write(f"{k}={env[k]}\n")
    try:
        spec = build_spec(values, env)
    except (ValueError, KeyError, OSError) as exc:
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
