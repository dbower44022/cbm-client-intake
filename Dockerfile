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

# The release tag (chapter network, Stamp A). A container has no .git, so the
# tag the release train pinned has to be baked in at build time and supplied by
# each deployment's spec as a RUN_AND_BUILD_TIME variable. Empty on a local or
# untagged build, which /healthz reports as null rather than guessing: `version`
# answers "what code is this", `releaseTag` answers "what promotion is this",
# and after a hotfix rebuild those two differ.
ARG RELEASE_TAG=""
ENV RELEASE_TAG=$RELEASE_TAG

# App Platform injects $PORT (default 8080); bind all interfaces.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", ".venv/bin/uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
