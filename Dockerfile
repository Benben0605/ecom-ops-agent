FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim

WORKDIR /app

# Keep the container resolver on the committed Python dependency graph. Install
# the pinned uv release from PyPI so the build does not require a second image
# registry in addition to Docker Hub.
RUN pip install --no-cache-dir uv==0.11.11

ENV PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev

COPY . .
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

EXPOSE 8000

# shell 形式才能展开 ${PORT}；Render 注入 PORT，本地 docker run 回落 8000
CMD uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8000}
