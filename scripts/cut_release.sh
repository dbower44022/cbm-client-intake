#!/usr/bin/env bash
#
# Cut a release tag — the chapter network's Stamp A.
#
# The release train leaves WEEKLY, Sunday 17:00 UTC (ruled 2026-08-26). That is
# roughly fifty tags a year, and the reason this script exists rather than a
# line in a runbook: if cutting a release is a half-hour ritual of remembering
# commands, fifty of them will not happen and the cadence quietly becomes "when
# someone remembers" — which is the failure mode the train exists to prevent.
#
# WHAT A TAG IS AND IS NOT. A tag is a marker. It changes no deployment,
# promotes nothing and breaks nothing, and it costs nothing to delete. Turning
# `deploy_on_push` off and moving a chapter to pinned-tag deploys is the large
# operational change, it lives in the release-train phase, and it is NOT this.
#
# The tag is what `releaseTag` reports at /healthz, supplied to the image as a
# RUN_AND_BUILD_TIME variable in each deployment's spec and baked in by the
# Dockerfile's RELEASE_TAG arg. `version` answers "what code is this";
# `releaseTag` answers "what promotion is this", and after a hotfix rebuild the
# two differ — which is the whole reason both exist.
#
# Format: v<version> matching pyproject.toml, so the two read against each
# other at a glance.
#
# It does NOT push. Pushing is Doug's, per the repo's standing convention; the
# push command is printed for you to run.
#
# Usage:  ./scripts/cut_release.sh            # cut the tag for the current version
#         ./scripts/cut_release.sh --dry-run  # say what it would do, touch nothing
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

die() { printf '\nERROR: %s\n' "$1" >&2; exit 1; }

# --- 1. The tree must be clean, and on main -------------------------------
# An annotated tag records a commit. Cutting one with uncommitted work in the
# tree produces a tag that does not describe anything anyone can check out.
#
# UNTRACKED files are deliberately not "dirty": nothing can put them in a
# commit, since the stamp below is committed with an explicit pathspec, so they
# cannot change what the tag names. Counting them cost a real cut — on
# 2026-09-13 another session held an untracked file, this script refused, and
# v0.226.0 was tagged by hand instead, going around the whole procedure.
[[ -n "$(git status --porcelain --untracked-files=no)" ]] && die "the working tree has uncommitted changes to tracked files. Commit or stash first — a tag must name a commit that exists."

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$BRANCH" != "main" ]]; then
  die "on branch '$BRANCH', not main. All three apps track main; a tag cut elsewhere names a commit no deployment will ever run."
fi

# --- 2. Read the version from pyproject, never from a human ---------------
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -1)"
[[ -z "$VERSION" ]] && die "could not read 'version' from pyproject.toml."
TAG="v$VERSION"

# --- 3. Refuse to move an existing tag ------------------------------------
# Re-pointing a tag someone may already have deployed is how "which version are
# you on" stops having an answer. Bump pyproject.toml instead.
if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  die "$TAG already exists (at commit $(git rev-parse --short "$TAG^{commit}")). Bump the version in pyproject.toml — never move a tag that may already be deployed."
fi

SHA="$(git rev-parse --short HEAD)"
SUBJECT="$(git log -1 --pretty=%s)"

if $DRY_RUN; then
  cat <<EOF

Dry run — nothing was created.

  would stamp        : release-tag.txt <- $TAG  (committed, then tagged)
  would tag          : $TAG
  at commit          : one new commit on top of $SHA  $SUBJECT
  would fast-forward : release -> $TAG
  then push          : git push origin $TAG release

EOF
  exit 0
fi

# --- 4. Stamp the tag into the source -------------------------------------
# A container has no .git, so the tag has to travel in the source. It used to
# travel as a RUN_AND_BUILD_TIME variable in every deployment's spec, which made
# promoting a deployment two operations rather than one — and when only the
# second was done, the deployment reported the PREVIOUS promotion as if it were
# the new one. The stamp is written HERE, into the commit the tag names, so the
# image carries it and promoting a deployment is one operation: build this commit.
#
# core.version.release_stamp honours it only when it matches pyproject's
# version — true at this commit, false at the next one — so main stops claiming
# a release as soon as it moves past one.
STAMP_FILE="release-tag.txt"
[[ -f "$STAMP_FILE" ]] || die "$STAMP_FILE is missing. It carries the release stamp into the image; restore it before cutting."
# Keep the file's explanatory header; replace only the value line below it.
{ grep '^#' "$STAMP_FILE"; echo "$TAG"; } > "$STAMP_FILE.new" && mv "$STAMP_FILE.new" "$STAMP_FILE"

if [[ -n "$(git status --porcelain -- "$STAMP_FILE")" ]]; then
  git add "$STAMP_FILE"
  git commit -q -m "chore(release): stamp $TAG

Written by scripts/cut_release.sh into the commit $TAG names, so the image
carries the release tag without a per-deployment environment variable."
  SHA="$(git rev-parse --short HEAD)"
else
  echo "release-tag.txt already reads $TAG; tagging the existing commit $SHA."
fi

# --- 4. Annotated, not lightweight ----------------------------------------
# Annotated carries the tagger and the date, which is what the fleet console
# wants when it reports who is on which promotion and since when.
git tag -a "$TAG" -m "Release $TAG

Cut from main at $SHA.
Stamped into release-tag.txt in this commit, so any deployment built from it
reports releaseTag=$TAG at /healthz with no per-deployment variable."

# --- 5. Fast-forward the release lane -------------------------------------
# Chapter apps track the `release` branch, never main (decided 2026-08-31):
# they must only ever see finished, named releases, and all the same one.
# Fast-forward ONLY — if release is not an ancestor of the tag, something
# rewrote history and a human must look.
if git rev-parse -q --verify refs/heads/release >/dev/null; then
  if git merge-base --is-ancestor release "$TAG^{commit}"; then
    git branch -f release "$TAG^{commit}"
  else
    die "the release branch is not an ancestor of $TAG — it cannot be fast-forwarded. Investigate before touching it."
  fi
else
  git branch release "$TAG^{commit}"
fi

cat <<EOF

Cut $TAG at $SHA ($SUBJECT); release fast-forwarded to it.

Push both:

    git push origin $TAG release

Then promote each deployment that should run it:

    uv run python scripts/promote.py <app-id> $TAG          # dry run
    uv run python scripts/promote.py <app-id> $TAG --apply

(Deployments whose Updates policy is Latest Stable and which track the
release branch with deploy_on_push on will rebuild on the push by
themselves — the promote script is for On Demand ones, and it also sets
RELEASE_TAG so /healthz reports the promotion honestly.)

EOF
