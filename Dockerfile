# Multi-stage: build the front end with Node, then package it with the API.
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --silent
COPY frontend ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY backend/pyproject.toml ./
COPY backend/rasad ./rasad
RUN pip install --no-cache-dir . && pip install --no-cache-dir "psycopg[binary]"
COPY --from=web /web/dist ./static
ENV RASAD_STATIC_DIR=/app/static RASAD_DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "rasad.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
