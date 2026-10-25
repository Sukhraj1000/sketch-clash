# syntax=docker/dockerfile:1
# Two images from one file:
#   docker build --target api .   FastAPI backend with CPU-only torch, YOLO11n and EasyOCR weights baked in
#   docker build --target web .   Built Vite frontend served by nginx, proxying /api to the backend
# compose.yaml builds and wires both. Secrets come from .env.local at run time, never from the image.

# ---------- backend ----------
FROM python:3.12-slim AS api
# opencv-python (pulled in by ultralytics) needs libGL and glib even when headless.
RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1 \
    YOLO_AUTOINSTALL=False \
    YOLO_CONFIG_DIR=/tmp/ultralytics \
    MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app
COPY backend/requirements.lock.txt backend/requirements.lock.txt
# --torch-backend cpu keeps the multi-GB CUDA wheels out of the image. uv is mounted
# for this step only, so the installer binary never ships in the runtime image.
RUN --mount=from=ghcr.io/astral-sh/uv:0.11.3,source=/uv,target=/bin/uv \
    uv pip install --system --torch-backend cpu -r backend/requirements.lock.txt
COPY backend/scripts/setup_vision.py backend/scripts/setup_vision.py
RUN python backend/scripts/setup_vision.py
COPY pytest.ini ./
COPY backend backend
RUN useradd --create-home --uid 1000 app \
 && mkdir -p backend/data \
 && chown -R app:app backend/data
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=5 \
  CMD python -c "import os,urllib.request;urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\",\"8000\")}/api/health',timeout=4)"
# PORT lets container hosts (Render, Cloud Run, Fly) choose the port; HOST=:: listens on IPv6 too,
# which Railway's private network needs. Graceful shutdown stays bounded because observatory SSE
# connections would otherwise keep an old worker alive.
CMD ["sh", "-c", "exec uvicorn backend.app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000} --proxy-headers --timeout-graceful-shutdown 5"]

# ---------- frontend build ----------
FROM node:24-alpine AS web-build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY index.html tsconfig.json vite.config.ts ./
COPY public public
COPY src src
RUN npm run build

# ---------- frontend server ----------
FROM nginx:1-alpine AS web
RUN apk upgrade --no-cache
ENV API_UPSTREAM=http://api:8000
COPY docker/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template
# Optional hosted password gate: set SITE_PASSWORD (and SITE_USER) to require basic auth.
COPY --chmod=755 docker/40-basic-auth.sh /docker-entrypoint.d/40-basic-auth.sh
COPY --from=web-build /app/dist /usr/share/nginx/html
EXPOSE 80
