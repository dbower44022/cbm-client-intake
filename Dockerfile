# Container image for the CBM Client Intake app (FastAPI + static wizard).
# Used by DigitalOcean App Platform; also runnable with plain `docker run`.
FROM python:3.12-slim

# uv for fast, reproducible installs from uv.lock.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first as a cached layer. The project itself is
# package = false (see pyproject.toml), so only deps are synced.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Application source.
COPY . .

# App Platform injects $PORT (default 8080); bind all interfaces.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", ".venv/bin/uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
