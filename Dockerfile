# Stage 1: build the React app.
FROM node:24-bookworm-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY handoff/config /src/handoff/config
COPY frontend/ ./
RUN npm run build

# Stage 2: FastAPI runtime (non-root) serving the API, SSE and the built SPA on one origin.
FROM python:3.12-slim AS runtime
# uv from PyPI (pinned): avoids a registry pull for a uv image.
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-compile uv==0.12.0
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
COPY handoff/config /app/handoff/config
COPY handoff/contracts /app/handoff/contracts
COPY handoff/fixtures /app/handoff/fixtures
COPY --from=frontend /src/frontend/dist /app/static
COPY scripts/entrypoint.sh /app/entrypoint.sh
RUN useradd --system --uid 10001 --no-create-home app
USER app
ENV PATH=/app/.venv/bin:$PATH HANDOFF_DIR=/app/handoff STATIC_DIR=/app/static
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
