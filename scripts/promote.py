#!/usr/bin/env python3
"""Promote ONE App Platform deployment to a release tag — the Update button's
worked example (chapter network, TASKS § R10; the button itself is proposal 8,
CRMBuilder's to build under its own process).

A promotion is TWO operations, deliberately in this order:

1. Set ``RELEASE_TAG=<tag>`` (scope RUN_AND_BUILD_TIME) on EVERY component of
   the app's spec — web, worker and the migrate job alike — and, unless
   ``--keep-branch``, point every component's ``github.branch`` at ``release``.
   Triggering a build without setting the variable makes ``/healthz`` report
   the PREVIOUS promotion as if it were the new one, which is worse than null.
2. Trigger a deployment and wait for it, then re-read ``/healthz`` and print
   the before/after ``releaseTag``.

Dry run by default: prints the plan and touches nothing. ``--status`` is the
read-only fleet signal Phase 2 asks for — the live spec's ``deploy_on_push``
and branch per component beside the app's reported release.

It reads the LIVE spec via doctl and edits only what it must — never a local
overlay file, so the encrypted-secrets regen trap does not arise
([[overlay-regen-encrypts-secrets]]): EV[...] values round-trip untouched.

Usage::

    uv run python scripts/promote.py <app-id> --status
    uv run python scripts/promote.py <app-id> v0.217.0            # dry run
    uv run python scripts/promote.py <app-id> v0.217.0 --apply

Exit codes: 0 done (or nothing to do); 1 the plan would change something and
this was a dry run; 2 the apply failed or was refused; 3 could not check.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request

COMPONENT_KINDS = ("services", "workers", "jobs")
RELEASE_BRANCH = "release"


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def doctl_json(args: list[str]) -> object:
    p = run(["doctl"] + args + ["--output", "json"])
    if p.returncode != 0:
        raise RuntimeError(f"doctl {' '.join(args)}: {p.stderr.strip()[:300]}")
    return json.loads(p.stdout)


def get_app(app_id: str) -> dict:
    apps = doctl_json(["apps", "get", app_id])
    return apps[0] if isinstance(apps, list) else apps


def healthz(url: str) -> dict:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/healthz", timeout=20) as r:
            return json.loads(r.read())
    except Exception as exc:  # noqa: BLE001 — reported, never raised past here
        return {"error": str(exc)}


def components(spec: dict):
    for kind in COMPONENT_KINDS:
        for comp in spec.get(kind) or []:
            yield kind, comp


def plan_changes(spec: dict, tag: str, keep_branch: bool) -> list[str]:
    """Mutates ``spec`` in place; returns the human-readable change list."""
    changes: list[str] = []
    for kind, comp in components(spec):
        name = comp.get("name", "?")
        envs = comp.setdefault("envs", [])
        row = next((e for e in envs if e.get("key") == "RELEASE_TAG"), None)
        if row is None:
            envs.append({"key": "RELEASE_TAG", "value": tag, "scope": "RUN_AND_BUILD_TIME"})
            changes.append(f"{name}: add RELEASE_TAG={tag} (RUN_AND_BUILD_TIME)")
        elif row.get("value") != tag or row.get("scope") != "RUN_AND_BUILD_TIME":
            changes.append(f"{name}: RELEASE_TAG {row.get('value')!r} -> {tag!r}")
            row["value"] = tag
            row["scope"] = "RUN_AND_BUILD_TIME"
        gh = comp.get("github")
        if gh and not keep_branch and gh.get("branch") != RELEASE_BRANCH:
            changes.append(f"{name}: branch {gh.get('branch')!r} -> {RELEASE_BRANCH!r}")
            gh["branch"] = RELEASE_BRANCH
    return changes


def remote_has_release_at(tag: str) -> tuple[bool, str]:
    heads = run(["git", "ls-remote", "origin",
                 f"refs/heads/{RELEASE_BRANCH}", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"])
    lines = dict(
        (ref.removeprefix("refs/heads/").removeprefix("refs/tags/"), sha)
        for sha, ref in (l.split("\t") for l in heads.stdout.strip().splitlines() if "\t" in l)
    )
    branch_sha = lines.get(RELEASE_BRANCH)
    # An annotated tag's own ref names the TAG OBJECT; the commit it marks is
    # the peeled "^{}" entry. Compare commits, or this refuses its own success.
    tag_sha = lines.get(f"{tag}^{{}}") or lines.get(tag)
    if not branch_sha:
        return False, f"origin has no '{RELEASE_BRANCH}' branch — push it first (cut_release.sh prints the command)"
    if not tag_sha:
        return False, f"origin has no tag {tag} — push it first"
    if branch_sha != tag_sha:
        return False, f"origin's '{RELEASE_BRANCH}' ({branch_sha[:7]}) is not at {tag} ({tag_sha[:7]}) — fast-forward and push it first"
    return True, ""


def cmd_status(app: dict) -> int:
    spec = app["spec"]
    url = app.get("live_url") or app.get("default_ingress") or ""
    h = healthz(url) if url else {"error": "no ingress"}
    print(f"app: {spec.get('name')}  ({app.get('id')})")
    print(f"reported: releaseTag={h.get('releaseTag')!r} version={h.get('version')!r} "
          f"crmConfig={((h.get('crmConfig') or {}).get('state'))!r} env={h.get('environment')!r}"
          + (f"  [healthz error: {h['error']}]" if "error" in h else ""))
    for kind, comp in components(spec):
        gh = comp.get("github") or {}
        row = next((e for e in (comp.get("envs") or []) if e.get("key") == "RELEASE_TAG"), None)
        print(f"  {kind[:-1]:<8} {comp.get('name', '?'):<16} branch={gh.get('branch')!r} "
              f"deploy_on_push={gh.get('deploy_on_push')} RELEASE_TAG={(row or {}).get('value')!r}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("app_id")
    ap.add_argument("tag", nargs="?", help="release tag, e.g. v0.217.0")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--status", action="store_true", help="read-only: policy signals per component")
    ap.add_argument("--keep-branch", action="store_true",
                    help="do not repoint github.branch at 'release' (e.g. promoting the soak copy)")
    ap.add_argument("--timeout", type=int, default=1200, help="seconds to wait for the deployment")
    args = ap.parse_args()

    try:
        app = get_app(args.app_id)
    except Exception as exc:  # noqa: BLE001
        print(f"could not read the app: {exc}", file=sys.stderr)
        return 3
    if args.status:
        return cmd_status(app)
    if not args.tag:
        print("a tag is required unless --status", file=sys.stderr)
        return 2

    spec = app["spec"]
    url = app.get("live_url") or app.get("default_ingress") or ""
    before = healthz(url) if url else {}
    changes = plan_changes(spec, args.tag, args.keep_branch)

    note = ""
    if not args.keep_branch:
        ok, why = remote_has_release_at(args.tag)
        if not ok and args.apply:
            print(f"REFUSED: {why}", file=sys.stderr)
            return 2
        if not ok:
            note = why

    print(f"app: {spec.get('name')}  reported releaseTag before: {before.get('releaseTag')!r}")
    if note:
        print(f"  note: --apply would refuse right now — {note}")
    if not changes:
        print("spec already names this promotion; nothing to change"
              + ("" if args.apply else " (a deployment would still be triggered with --apply)"))
    for c in changes:
        print(f"  would: {c}" if not args.apply else f"  {c}")
    if not args.apply:
        print("\ndry run — nothing was written. Re-run with --apply.")
        return 1 if changes else 0

    import tempfile

    import yaml
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        yaml.safe_dump(spec, fh, sort_keys=False)
        spec_path = fh.name
    p = run(["doctl", "apps", "update", args.app_id, "--spec", spec_path], timeout=300)
    if p.returncode != 0:
        print(f"spec update failed: {p.stderr.strip()[:400]}", file=sys.stderr)
        return 2
    p = run(["doctl", "apps", "create-deployment", args.app_id, "--output", "json"], timeout=120)
    if p.returncode != 0:
        # the spec update itself usually triggers a build; a conflict here means one is already running
        print(f"create-deployment: {p.stderr.strip()[:200]} — following the in-progress one")
    print("deployment triggered; waiting…")
    deadline = time.time() + args.timeout
    phase = "?"
    while time.time() < deadline:
        time.sleep(20)
        try:
            dep = doctl_json(["apps", "list-deployments", args.app_id])[0]
        except Exception:  # noqa: BLE001
            continue
        phase = dep.get("phase", "?")
        if phase in ("ACTIVE", "ERROR", "CANCELED", "SUPERSEDED"):
            break
        print(f"  {phase.lower()}…")
    after = healthz(url) if url else {}
    print(f"deployment phase: {phase}")
    print(f"reported releaseTag: {before.get('releaseTag')!r} -> {after.get('releaseTag')!r}"
          f" (version {after.get('version')!r}, crmConfig {((after.get('crmConfig') or {}).get('state'))!r})")
    if phase != "ACTIVE" or after.get("releaseTag") != args.tag:
        print("the promotion did NOT land as asked — the previous release is what is in force", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
