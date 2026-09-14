#!/usr/bin/env python3
"""Set ONE App Platform deployment's Updates policy — the policy half of the
Update button (chapter network, TASKS § R10; the button is proposal 8,
CRMBuilder's to build under its own process).

The three policy values are the ones the release-train phase names:

===============  ==================================  ==========================
Policy           Branch, deploy_on_push              Who it is for
===============  ==================================  ==========================
development      ``main``, on                        the one soak copy
latest-stable    ``release``, on                     the chapter default
on-demand        ``release``, off                    a deployment held back
===============  ==================================  ==========================

**Why a policy is a script and not a note.** A deployment has three components —
``web``, ``delivery-worker`` and the ``PRE_DEPLOY`` job ``migrate`` — each with
its own ``github`` block. Setting one and not the others half-updates the app,
and nothing on the platform tells you that you did. This sets all of them and
reads the result back.

**It also drops a stale ``RELEASE_TAG``.** The release tag used to be supplied
per deployment as a ``RUN_AND_BUILD_TIME`` variable; it now travels in the
source (``release-tag.txt``, written by ``scripts/cut_release.sh``). An
environment variable still overrides the file, so one left behind freezes the
deployment's reported promotion at whatever it last said while the code moves on
— which is the misreport the two stamps exist to prevent. ``--keep-release-tag``
retains it for a deployment that is deliberately pinned by hand.

**A policy change does not move the app to the branch tip.** A spec update
triggers a deployment that rebuilds the **same source commit** with the new
configuration — measured on `lakeside-intake` 2026-09-13, where turning
Latest Stable on redeployed the commit it was already running rather than the
`release` tip pushed ten minutes earlier. That is usually right (a policy change
is not a promotion), but on the transition *into* Latest Stable it leaves the
app behind. ``--deploy`` triggers a source-fetching deployment afterwards; the
script says so either way. Ordinary Sundays need none of this: the push to
`release` is itself the trigger, and a push does re-resolve the branch.

Dry run by default: prints the plan and touches nothing. ``--status`` is the
read-only detector Phase 5 asked for — the live spec compared against a policy,
which is how you find "latest-stable, but ``deploy_on_push`` is off".

It reads the LIVE spec via doctl and edits only what it must, never a local
overlay file, so the encrypted-secrets regen trap does not arise
([[overlay-regen-encrypts-secrets]]): ``EV[...]`` values round-trip untouched.

Usage::

    uv run python scripts/set_updates_policy.py <app-id> --status
    uv run python scripts/set_updates_policy.py <app-id> latest-stable
    uv run python scripts/set_updates_policy.py <app-id> latest-stable --apply

Exit codes: 0 done (or already conformant); 1 the plan would change something
and this was a dry run; 2 the apply failed or was refused; 3 could not check.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

COMPONENT_KINDS = ("services", "workers", "jobs")

#: policy name -> (branch, deploy_on_push)
POLICIES: dict[str, tuple[str, bool]] = {
    "development": ("main", True),
    "latest-stable": ("release", True),
    "on-demand": ("release", False),
}


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


def components(spec: dict):
    for kind in COMPONENT_KINDS:
        for comp in spec.get(kind) or []:
            yield kind, comp


def plan_changes(spec: dict, branch: str, on_push: bool, drop_tag: bool) -> list[str]:
    """Edit the spec in place; return a human-readable list of what changed."""
    changes: list[str] = []
    for _kind, comp in components(spec):
        name = comp.get("name", "?")
        gh = comp.get("github")
        if gh is None:
            # A component built from a registry or a Dockerfile source has no
            # branch to track; say so rather than inventing a github block.
            changes.append(f"{name}: SKIPPED — no github source on this component")
            continue
        if gh.get("branch") != branch:
            changes.append(f"{name}: branch {gh.get('branch')!r} -> {branch!r}")
            gh["branch"] = branch
        # An unset deploy_on_push reads as off on the platform but as None here.
        if bool(gh.get("deploy_on_push")) != on_push:
            changes.append(
                f"{name}: deploy_on_push {gh.get('deploy_on_push')!r} -> {on_push}"
            )
        gh["deploy_on_push"] = on_push
        if drop_tag:
            envs = comp.get("envs") or []
            stale = [e for e in envs if e.get("key") == "RELEASE_TAG"]
            if stale:
                changes.append(
                    f"{name}: drop RELEASE_TAG={stale[0].get('value')!r} "
                    f"(the stamp now travels in release-tag.txt)"
                )
                comp["envs"] = [e for e in envs if e.get("key") != "RELEASE_TAG"]
    return changes


def cmd_status(app: dict, policy: str | None) -> int:
    spec = app["spec"]
    print(f"app: {spec.get('name')}  ({app.get('id')})")
    want = POLICIES.get(policy or "")
    drift = 0
    for kind, comp in components(spec):
        gh = comp.get("github") or {}
        tag = next(
            (e for e in (comp.get("envs") or []) if e.get("key") == "RELEASE_TAG"), None
        )
        line = (
            f"  {kind[:-1]:8} {comp.get('name', '?'):16} branch={gh.get('branch')!r} "
            f"deploy_on_push={gh.get('deploy_on_push')} RELEASE_TAG={(tag or {}).get('value')!r}"
        )
        if want and (gh.get("branch") != want[0] or bool(gh.get("deploy_on_push")) != want[1]):
            line += f"   <- NOT {policy}"
            drift += 1
        print(line)
    if want and not drift:
        print(f"conformant with '{policy}'")
    elif want:
        print(f"{drift} component(s) do not match '{policy}'")
    return 1 if drift else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("app_id")
    ap.add_argument("policy", nargs="?", choices=sorted(POLICIES),
                    help="development | latest-stable | on-demand")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--status", action="store_true",
                    help="read-only: the live spec, flagged against POLICY if given")
    ap.add_argument("--deploy", action="store_true",
                    help="after applying, trigger a deployment that fetches the branch tip "
                         "(a spec update alone rebuilds the same commit)")
    ap.add_argument("--keep-release-tag", action="store_true",
                    help="leave a RELEASE_TAG variable in place (a hand-pinned deployment)")
    args = ap.parse_args()

    try:
        app = get_app(args.app_id)
    except Exception as exc:  # noqa: BLE001
        print(f"could not read the app: {exc}", file=sys.stderr)
        return 3
    if args.status:
        return cmd_status(app, args.policy)
    if not args.policy:
        print("a policy is required unless --status", file=sys.stderr)
        return 2

    spec = app["spec"]
    branch, on_push = POLICIES[args.policy]
    changes = plan_changes(spec, branch, on_push, not args.keep_release_tag)

    print(f"app: {spec.get('name')}  policy: {args.policy} "
          f"(branch {branch!r}, deploy_on_push {on_push})")
    if not changes:
        print("already conformant; nothing to change")
        return 0
    for c in changes:
        print(f"  would: {c}" if not args.apply else f"  {c}")
    if not args.apply:
        print("\ndry run — nothing was written. Re-run with --apply.")
        return 1

    import tempfile

    import yaml

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        yaml.safe_dump(spec, fh, sort_keys=False)
        spec_path = fh.name
    p = run(["doctl", "apps", "update", args.app_id, "--spec", spec_path], timeout=300)
    if p.returncode != 0:
        print(f"spec update failed: {p.stderr.strip()[:400]}", file=sys.stderr)
        return 2

    if args.deploy:
        d = run(["doctl", "apps", "create-deployment", args.app_id], timeout=120)
        print("deployment triggered" if d.returncode == 0
              else f"could not trigger a deployment: {d.stderr.strip()[:200]}")
    else:
        print("\nNOTE: the spec update rebuilds the SAME commit with the new settings.\n"
              "      To move this app to the branch tip now, re-run with --deploy or:\n"
              f"        doctl apps create-deployment {args.app_id}\n"
              "      From here on a push to the tracked branch triggers it by itself.")

    # Read it back: a spec update that reports success but stores something else
    # is the failure this whole script exists to make visible.
    try:
        return cmd_status(get_app(args.app_id), args.policy)
    except Exception as exc:  # noqa: BLE001
        print(f"applied, but could not read the app back: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
