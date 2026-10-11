FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src ./src
RUN npm run build

FROM python:3.13-slim-bookworm AS dependencies
COPY --from=ghcr.io/astral-sh/uv:0.7.20 /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM python:3.13-slim-bookworm AS runtime
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app/backend" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY --from=dependencies /app/.venv /app/.venv
COPY backend/app ./backend/app
COPY backend/migrations ./backend/migrations
COPY alembic.ini ./
COPY --from=frontend /build/frontend/dist ./frontend/dist
USER 10001:10001
EXPOSE 8017
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8017/api/health', timeout=3)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8017", "--workers", "1", "--no-access-log", "--no-proxy-headers"]
