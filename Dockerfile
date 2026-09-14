# Container image for the CBM Client Intake app (FastAPI + static wizard).
# Used by DigitalOcean App Platform; also runnable with plain `docker run`.
#
# Base images are PINNED (Phase 6, reliability review 2026-07-17): floating
# tags meant a rebuild months later could get a different toolchain than the
# build that was verified. Bump both pins DELIBERATELY (build + test locally,
# then commit); the uv pin matches the version that generated uv.lock
# (lockfile revision compatibility).
FROM python:3.12.8-slim

# uv for fast, reproducible installs from uv.lock.
COPY --from=ghcr.io/astral-sh/uv:0.10.6 /uv /uvx /bin/

WORKDIR /app

# Install dependencies first as a cached layer. The project itself is
# package = false (see pyproject.toml), so only deps are synced.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Application source.
COPY . .

# The release tag (chapter network, Stamp A) normally travels in the SOURCE:
# release-tag.txt, written by scripts/cut_release.sh into the commit the tag
# names and copied in above. Nothing needs to be passed at build time, which is
# what makes promoting a deployment one operation rather than two.
#
# This ARG stays as an override for a build that is not a release commit but
# must still claim a tag. A NON-EMPTY environment value wins over the file; an
# empty one is treated as an absence, because this ENV line sets the variable
# on every image whether or not anyone passed an argument (v0.228.0 shipped
# before that was handled, and every deployment reported no release at all).
# Use the override deliberately: a stale value here makes the deployment report
# the PREVIOUS promotion as if it were the new one, which is worse than none.
ARG RELEASE_TAG=""
ENV RELEASE_TAG=$RELEASE_TAG

# App Platform injects $PORT (default 8080); bind all interfaces.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", ".venv/bin/uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
