# syntax=docker/dockerfile:1

# ---- 1. Build the SPA ----
FROM node:24-alpine AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Python runtime ----
FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app/backend
# Tesseract OCR for scanned documents and photos (runs locally; uploaded files never leave the server).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/ ./
COPY data/ /app/data/
COPY --from=web /app/frontend/dist /app/frontend/dist
RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app
ENV STATIC_DIR=/app/frontend/dist
EXPOSE 8000
# Render/Railway/Fly inject $PORT; locally it defaults to 8000. The demo seed runs only with DEMO_MODE=true.
# The same image runs the background worker: command ["python", "-m", "app.worker"].
CMD ["sh", "scripts/start.sh"]
