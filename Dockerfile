# Two stages: build the frontend with Node, then serve it from the Python image
# alongside the API. One container, one origin — which also means the browser
# never makes a cross-origin request, so CORS stops being a consideration in
# production the way it is under the Vite dev proxy.

# ---------- frontend ----------
FROM node:22-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# ---------- backend ----------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so a code change does not reinstall the world.
COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir \
        "fastapi>=0.115" "uvicorn[standard]>=0.32" "sqlalchemy>=2.0" \
        "psycopg[binary]>=3.2" "alembic>=1.14" "pydantic>=2.9" \
        "pydantic-settings>=2.6" "httpx>=0.27" "itsdangerous>=2.2"

COPY backend/ ./
COPY --from=frontend /build/dist ./static

# Migrations run on start rather than at build time: the database does not
# exist during the build, and running them here keeps a fresh volume working
# without a separate manual step.
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
