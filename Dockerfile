# syntax=docker/dockerfile:1
# Multi-stage image: Node builds the React app, Python 3.12 serves the API and the built app.

FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Firebase web config: public by design; build arguments from GitLab variables (no dev token in images)
ARG VITE_FIREBASE_API_KEY VITE_FIREBASE_AUTH_DOMAIN VITE_FIREBASE_PROJECT_ID=mojo-picon VITE_FIREBASE_APP_ID
ENV VITE_FIREBASE_API_KEY=$VITE_FIREBASE_API_KEY VITE_FIREBASE_AUTH_DOMAIN=$VITE_FIREBASE_AUTH_DOMAIN \
    VITE_FIREBASE_PROJECT_ID=$VITE_FIREBASE_PROJECT_ID VITE_FIREBASE_APP_ID=$VITE_FIREBASE_APP_ID
RUN npm run build

FROM python:3.12-slim AS app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv PATH="/app/.venv/bin:$PATH"
WORKDIR /app
# Dependencies first (cached layer), then the project; no dev or data-build dependencies
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ src/
COPY data/foods.csv data/met_table.csv data/household_measures.csv data/household_measure_definitions.csv data/recipes.yaml data/
COPY knowledge/ knowledge/
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist /app/frontend/dist

ENV ENVIRONMENT=production FRONTEND_DIR=/app/frontend/dist PORT=8080
RUN useradd --uid 10001 --no-create-home app
USER app
EXPOSE 8080
CMD ["sh", "-c", "uvicorn mojo_picon.api.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers"]
