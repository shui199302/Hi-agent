# syntax=docker/dockerfile:1.7

FROM node:22.17.0-bookworm-slim AS web-builder
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
WORKDIR /build/web
RUN corepack enable && corepack prepare pnpm@11.7.0 --activate
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

FROM ghcr.io/astral-sh/uv:0.8.12 AS uv

FROM python:3.12.11-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    HI_AGENT_HOST=127.0.0.1 \
    HI_AGENT_PORT=8787 \
    HI_AGENT_DATA_DIR=/app/data \
    HI_AGENT_WEB_DIST_DIR=/app/web/dist \
    HI_AGENT_SKILLS_DIR=/app/skills
RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin hiagent
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
COPY backend/ /app/backend/
RUN uv sync --directory /app/backend --frozen --no-dev --no-editable
COPY mcp_servers/ /app/mcp_servers/
RUN uv sync --directory /app/mcp_servers --frozen --no-dev --no-editable
COPY --from=web-builder /build/web/dist /app/web/dist
COPY skills/ /app/skills/
RUN mkdir -p /app/data && chown -R hiagent:hiagent /app/data
USER hiagent
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["/app/backend/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/v1/health', timeout=3).read()"]
# Bind inside the container; app-compose publishes it only on the host loopback.
CMD ["/app/backend/.venv/bin/uvicorn", "hi_agent.main:app", "--app-dir", "/app/backend/src", "--host", "0.0.0.0", "--port", "8787"]
