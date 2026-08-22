"""Restore the crm-test EspoCRM instance to its golden training baseline.

crm-test doubles as CBM's training sandbox, so it has to come back pristine
every morning WITHOUT throwing away the two other jobs that instance does:
the CRM team edits its schema under the live app, and it is the only
pre-production review gate this project has.

Both survive because of where EspoCRM keeps things:

* **Entity Manager output is FILES**, under
  ``data/espocrm/custom/Espo/Custom/Resources/`` (entityDefs, layouts,
  aclDefs, scopes, formula...).  This script never touches them.  It restores
  the record tables and then runs ``rebuild``, so the schema re-derives from
  whatever metadata is live at that moment — a field the CRM team adds at 3pm
  still exists at 00:05, with its data cleared, which is what a sandbox wants.
* **Config and identity are DB ROWS.**  Those are the ``KEEP_TABLES`` below:
  roles, teams, email templates, scheduled jobs, portals, reports, workflow
  definitions and — critically — the Google/mailbox credentials
  (``integration``, ``external_account``, ``o_auth_*``, ``app_secret``,
  ``inbound_email``).  Everything else resets.

The list is deliberately KEEP-by-exception: a new custom entity from the CRM
team is not in ``KEEP_TABLES``, so it is correctly treated as records with no
one having to remember to update anything.

Every reset table is restored from ONE atomic dump, so cross-table consistency
(``user`` ↔ ``entity_email_address`` ↔ ``email_address`` ...) always holds.

This covers the CRM half only.  The app's own Postgres — the /ops queue,
record comments, the Drive index — resets in step on the worker side, which
keeps that logic in the repo where migrations can evolve it.  See
``SANDBOX-RESET.md``.

Runs ON THE DROPLET (stdlib only, Python 3.10, no venv).  Refuses to run
against anything whose site URL is not crm-test.

    python3 reset_crm_sandbox.py status
    python3 reset_crm_sandbox.py baseline --apply    # capture the golden state
    python3 reset_crm_sandbox.py reset               # dry run — says what it would do
    python3 reset_crm_sandbox.py reset --apply       # what cron runs

A ``.sandbox-hold`` file in the EspoCRM home directory skips that night's
reset, for when someone is mid-review and wants their state to survive.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

HOME = Path("/var/www/espocrm")
GOLDEN = Path("/var/lib/cbm-sandbox/golden")
LOG = Path("/var/log/cbm-sandbox-reset.log")
HOLD = HOME / ".sandbox-hold"

DB_CONTAINER = "espocrm-db"
APP_CONTAINER = "espocrm"
DAEMON_CONTAINER = "espocrm-daemon"
DB_NAME = "espocrm"

# Guard: this script must never be pointed at production.
REQUIRED_SITE_URL_MARKER = "crm-test"

#: Runtime noise: never captured into the baseline, TRUNCATED on every reset.
#: Distinct from KEEP_TABLES, which is left untouched — these are emptied.
#:
#: Found the hard way (2026-08-22): the first baseline was 62 MB compressed and
#: 660 MB raw, of which `job` was 314 MB, `auth_log_record` 190 MB and
#: `scheduled_job_log_record` 159 MB. Beyond the waste, restoring `job` nightly
#: re-inserts old queued jobs for the EspoCRM daemon to pick up — a reset that
#: makes the CRM *do* things is not a reset. `auth_log_record` also carries the
#: login history of real people from before the sandbox was purged.
#:
#: The native `email` tables are here too: the app stores correspondence in
#: CConversation/CCommunication and never reads these, and their contents
#: predate the purge and cannot be inspected with the app's API key.
RUNTIME_TABLES: frozenset[str] = frozenset(
    {
        "job", "scheduled_job_log_record", "auth_log_record", "app_log_record",
        "action_history_record", "notification", "email_queue_item",
        "webhook_queue_item", "webhook_event_queue_item", "workflow_log_record",
        "bpmn_process", "bpmn_flow_node", "bpmn_user_task",
        "import", "import_entity", "import_error", "export", "mass_action",
        "auth_token", "two_factor_code", "password_change_request",
        "email", "email_user", "email_email_address", "email_email_account",
        "email_inbound_email",
    }
)

#: Tables that survive a reset — config, identity definitions and credentials.
#: Everything NOT listed here is record data and is restored from the golden
#: dump.  Grouped by why, because the "why" is what a future reader needs when
#: deciding where a new table belongs.
KEEP_TABLES = frozenset(
    {
        # --- access-control definitions (memberships reset with the users) ---
        "team", "role", "role_team", "portal", "portal_role", "portal_report",
        # --- authored artefacts staff/the CRM team build up over time ---
        "email_template", "email_template_category", "email_template_category_path",
        "template", "dashboard_template", "layout_record", "layout_set",
        "knowledge_base_article", "knowledge_base_article_knowledge_base_category",
        "knowledge_base_article_portal", "knowledge_base_category",
        "knowledge_base_category_path",
        "report", "report_category", "report_category_path", "report_filter",
        "report_panel", "report_target_list", "report_user",
        "workflow", "workflow_category", "workflow_category_path",
        "workflow_round_robin", "team_workflow",
        "bpmn_flowchart", "bpmn_flowchart_category", "bpmn_flowchart_category_path",
        "bpmn_signal_listener",
        "document_folder", "document_folder_path",
        "target_list_category", "target_list_category_path",
        # --- credentials and integration wiring: losing these breaks the app ---
        "authentication_provider", "integration", "external_account",
        "o_auth_provider", "o_auth_account", "app_secret", "extension",
        "inbound_email", "inbound_email_team", "email_account", "email_filter",
        "email_folder", "group_email_folder", "group_email_folder_team",
        "webhook",
        # --- instance-level reference data and bookkeeping ---
        "system_data", "next_number", "unique_id",
        "currency", "currency_record", "currency_record_rate", "address_country",
        "scheduled_job", "working_time_calendar",
        "working_time_calendar_working_time_range", "working_time_range",
    }
)


# --------------------------------------------------------------------------
# plumbing
# --------------------------------------------------------------------------

def log(message: str) -> None:
    """Write to stdout and to the persistent reset log (cron's only witness)."""
    line = f"{dt.datetime.now().isoformat(timespec='seconds')}  {message}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass  # never let logging be the thing that fails a reset


def compose_value(key: str) -> str:
    """Read one value out of docker-compose.yml.

    The MariaDB root password lives there; this is how the script gets it
    without a second copy of the secret on disk.  It is passed to the client
    through ``MYSQL_PWD`` and never appears in a command line or the log.
    """
    for raw in (HOME / "docker-compose.yml").read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped.startswith(f"{key}:"):
            return stripped.split(":", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"ERROR: {key} not found in docker-compose.yml")


def sql(statement: str) -> str:
    """Run one statement as root and return raw tab-separated output."""
    proc = subprocess.run(
        ["docker", "exec", "-e", f"MYSQL_PWD={DB_PASSWORD}", DB_CONTAINER,
         "mariadb", "-uroot", "-N", "-B", DB_NAME, "-e", statement],
        capture_output=True, text=True, check=True,
    )
    return proc.stdout


def live_tables() -> set[str]:
    out = sql(
        "select table_name from information_schema.tables "
        f"where table_schema='{DB_NAME}';"
    )
    return {line.strip() for line in out.splitlines() if line.strip()}


def guard_not_production() -> None:
    """Refuse to run anywhere the site URL is not crm-test."""
    site_url = compose_value("ESPOCRM_CONFIG_SITE_URL")
    if REQUIRED_SITE_URL_MARKER not in site_url:
        raise SystemExit(
            f"REFUSING: site URL {site_url!r} does not contain "
            f"{REQUIRED_SITE_URL_MARKER!r}. This script only resets the sandbox."
        )


# --------------------------------------------------------------------------
# baseline
# --------------------------------------------------------------------------

def cmd_baseline(apply: bool) -> int:
    """Capture the golden state: the record tables, the config tables and the
    attachment files, plus a manifest describing what was taken.

    Deliberately manual.  Nothing re-baselines on a schedule, so a day's
    training mess can never be silently promoted into the pristine state.
    """
    guard_not_production()
    tables = live_tables()
    records = sorted(tables - KEEP_TABLES - RUNTIME_TABLES)
    config = sorted(tables & KEEP_TABLES)
    runtime = sorted(tables & RUNTIME_TABLES)
    upload = HOME / "data" / "espocrm" / "data" / "upload"

    log(f"baseline: {len(records)} record tables, {len(config)} config tables, "
        f"{len(runtime)} runtime tables excluded")
    log(f"baseline: attachments from {upload}")
    if not apply:
        log("baseline: DRY RUN — nothing written. Re-run with --apply.")
        return 0

    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    GOLDEN.mkdir(parents=True, exist_ok=True)

    _dump(records, GOLDEN / "records.sql.gz", single_transaction=True)
    # Config is captured for disaster recovery only — a reset never restores it.
    _dump(config, GOLDEN / "config-reference.sql.gz", single_transaction=True)

    archive = GOLDEN / "upload.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        if upload.is_dir():
            tar.add(upload, arcname="upload")
    log(f"baseline: wrote {archive} ({archive.stat().st_size // 1024} KiB)")

    manifest = {
        "captured": stamp,
        "record_tables": records,
        "config_tables_excluded": config,
        "runtime_tables_excluded": runtime,
        "site_url": compose_value("ESPOCRM_CONFIG_SITE_URL"),
    }
    (GOLDEN / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"baseline: captured at {stamp} -> {GOLDEN}")
    return 0


def _dump(tables: list[str], target: Path, *, single_transaction: bool) -> None:
    """mariadb-dump the named tables into a gzip file, atomically."""
    if not tables:
        log(f"dump: no tables for {target.name} — skipped")
        return
    args = ["docker", "exec", "-e", f"MYSQL_PWD={DB_PASSWORD}", DB_CONTAINER,
            "mariadb-dump", "-uroot", "--add-drop-table"]
    if single_transaction:
        args.append("--single-transaction")
    args += [DB_NAME, *tables]
    tmp = target.with_suffix(".part")
    with tmp.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb") as gz:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE)
        assert proc.stdout is not None
        shutil.copyfileobj(proc.stdout, gz)
        if proc.wait() != 0:
            tmp.unlink(missing_ok=True)
            raise SystemExit(f"ERROR: mariadb-dump failed for {target.name}")
    tmp.replace(target)
    log(f"dump: wrote {target.name} ({target.stat().st_size // 1024} KiB, {len(tables)} tables)")


# --------------------------------------------------------------------------
# reset
# --------------------------------------------------------------------------

def cmd_reset(apply: bool) -> int:
    guard_not_production()

    if HOLD.exists():
        log(f"reset: HELD — {HOLD} exists. Nothing done.")
        return 0

    manifest_path = GOLDEN / "manifest.json"
    records_dump = GOLDEN / "records.sql.gz"
    if not manifest_path.exists() or not records_dump.exists():
        log(f"reset: no golden baseline in {GOLDEN}. Run 'baseline --apply' first.")
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    golden_tables = set(manifest["record_tables"])
    tables = live_tables()

    # Entities the CRM team added since the baseline: not in the dump, so the
    # import cannot clear them. Truncate them instead — they hold records.
    newer = sorted((tables - KEEP_TABLES - RUNTIME_TABLES) - golden_tables)
    # Runtime tables are never in the dump, so the import cannot clear them.
    runtime = sorted(tables & RUNTIME_TABLES)
    # Entities removed since the baseline: the import recreates them. Harmless,
    # and a rebuild leaves them inert, but say so rather than doing it silently.
    stale = sorted(golden_tables - tables)

    log(f"reset: baseline of {manifest['captured']}, {len(golden_tables)} record tables")
    if newer:
        log(f"reset: {len(newer)} table(s) newer than the baseline will be truncated: {', '.join(newer)}")
    if stale:
        log(f"reset: {len(stale)} table(s) in the baseline no longer live: {', '.join(stale)}")

    if not apply:
        log("reset: DRY RUN — nothing changed. Re-run with --apply.")
        return 0

    log("reset: pausing the EspoCRM daemon")
    subprocess.run(["docker", "stop", DAEMON_CONTAINER], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wipe = newer + runtime
        if wipe:
            statements = "set foreign_key_checks=0; " + " ".join(
                f"truncate table `{name}`;" for name in wipe
            ) + " set foreign_key_checks=1;"
            sql(statements)
            log(f"reset: truncated {len(newer)} post-baseline and "
                f"{len(runtime)} runtime table(s)")

        log("reset: importing the golden record tables")
        _import(records_dump)

        log("reset: restoring attachment files")
        _restore_uploads()

        log("reset: rebuilding (schema re-derives from the live custom metadata)")
        subprocess.run(
            ["docker", "exec", "-u", "www-data", APP_CONTAINER, "php", "command.php", "rebuild"],
            check=False,
        )
        subprocess.run(
            ["docker", "exec", "-u", "www-data", APP_CONTAINER, "php", "command.php", "clear-cache"],
            check=False,
        )
    finally:
        subprocess.run(["docker", "start", DAEMON_CONTAINER], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log("reset: daemon resumed")

    log("reset: complete")
    return 0


def _import(dump: Path) -> None:
    args = ["docker", "exec", "-i", "-e", f"MYSQL_PWD={DB_PASSWORD}", DB_CONTAINER,
            "mariadb", "-uroot", DB_NAME]
    with gzip.open(dump, "rb") as gz:
        proc = subprocess.Popen(args, stdin=subprocess.PIPE)
        assert proc.stdin is not None
        shutil.copyfileobj(gz, proc.stdin)
        proc.stdin.close()
        if proc.wait() != 0:
            raise SystemExit("ERROR: importing the golden dump failed")


def _restore_uploads() -> None:
    """Replace data/upload with the golden copy.

    Attachments are rows AND files; restoring the table without the files
    leaves every golden record pointing at a missing document.
    """
    archive = GOLDEN / "upload.tar.gz"
    if not archive.exists():
        log("reset: no golden upload archive — attachment files left as they are")
        return
    data_dir = HOME / "data" / "espocrm" / "data"
    live = data_dir / "upload"
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(data_dir)          # writes data/upload
    # tar wrote straight over the live dir; make ownership match the container.
    subprocess.run(["chown", "-R", "1000:1000", str(live)], check=False)


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------

def cmd_status(_apply: bool) -> int:
    guard_not_production()
    tables = live_tables()
    manifest_path = GOLDEN / "manifest.json"
    log(f"status: site {compose_value('ESPOCRM_CONFIG_SITE_URL')}")
    log(f"status: {len(tables)} tables live — "
        f"{len(tables - KEEP_TABLES - RUNTIME_TABLES)} record, "
        f"{len(tables & KEEP_TABLES)} config (kept), "
        f"{len(tables & RUNTIME_TABLES)} runtime (truncated)")
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        log(f"status: golden baseline captured {manifest['captured']}")
    else:
        log(f"status: NO golden baseline in {GOLDEN}")
    log(f"status: hold sentinel {'PRESENT — resets are paused' if HOLD.exists() else 'absent'}")
    return 0


def cmd_deleted(_apply: bool) -> int:
    """Report rows still sitting in the database as soft-deleted.

    EspoCRM never hard-deletes on the spot: a delete sets ``deleted=1`` and the
    Cleanup job removes the row only once it is older than
    ``cleanupDeletedRecordsPeriod`` (three months by default).  That matters
    here because a golden baseline captured straight after a purge would carry
    every purged record's data forward indefinitely.
    """
    guard_not_production()
    out = sql(
        "select table_name from information_schema.columns "
        f"where table_schema='{DB_NAME}' and column_name='deleted' order by table_name;"
    )
    tables = [line.strip() for line in out.splitlines() if line.strip()]
    if not tables:
        log("deleted: no table has a `deleted` column")
        return 0
    # One statement per table: a single UNION over ~180 tables exceeds
    # MariaDB's limit on tables per query and fails outright.
    counts: list[tuple[str, int]] = []
    for name in tables:
        out = sql(f"select count(*) from `{name}` where deleted=1;")
        value = int((out.strip() or "0").splitlines()[0])
        if value:
            counts.append((name, value))
    for name, value in sorted(counts, key=lambda pair: -pair[1]):
        log(f"deleted: {name:32} {value}")
    log(f"deleted: {sum(v for _, v in counts)} soft-deleted row(s) "
        f"across {len(tables)} tables")
    return 0


def cmd_purge_deleted(apply: bool) -> int:
    """Hard-delete every soft-deleted row, so the baseline does not carry them.

    EspoCRM's own Cleanup job only removes rows older than
    ``cleanupDeletedRecordsPeriod`` (three months by default), which is no use
    immediately after a purge — and a golden baseline captured with them still
    present would restore the deleted data every night, forever. These rows are
    already invisible to every user; this just stops them being immortalised.

    Run before ``baseline``, never on a whim: it also discards anything sitting
    in the CRM's own trash awaiting restore.
    """
    guard_not_production()
    out = sql(
        "select table_name from information_schema.columns "
        f"where table_schema='{DB_NAME}' and column_name='deleted' order by table_name;"
    )
    tables = [line.strip() for line in out.splitlines() if line.strip()]
    total = 0
    plan: list[tuple[str, int]] = []
    for name in tables:
        count = int((sql(f"select count(*) from `{name}` where deleted=1;").strip()
                     or "0").splitlines()[0])
        if count:
            plan.append((name, count))
            total += count
    for name, count in sorted(plan, key=lambda pair: -pair[1]):
        log(f"purge-deleted: {name:32} {count}")
    log(f"purge-deleted: {total} soft-deleted row(s) across {len(plan)} table(s)")
    if not apply:
        log("purge-deleted: DRY RUN — nothing removed. Re-run with --apply.")
        return 0
    for name, _count in plan:
        sql(f"delete from `{name}` where deleted=1;")
    log(f"purge-deleted: removed {total} row(s)")
    return 0


COMMANDS = {
    "baseline": cmd_baseline,
    "reset": cmd_reset,
    "status": cmd_status,
    "deleted": cmd_deleted,
    "purge-deleted": cmd_purge_deleted,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument(
        "--apply", action="store_true",
        help="actually make the change (everything is a dry run without it)",
    )
    args = parser.parse_args()
    return COMMANDS[args.command](args.apply)


if __name__ == "__main__":
    DB_PASSWORD = compose_value("MARIADB_ROOT_PASSWORD")
    sys.exit(main())
