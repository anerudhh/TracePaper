# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS frontend
WORKDIR /build/web
COPY web/package*.json ./
RUN --mount=type=secret,id=proxy_ca if [ -f /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY requirements.lock ./
RUN --mount=type=secret,id=proxy_ca if [ -f /run/secrets/proxy_ca ]; then PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r requirements.lock; else pip install --no-cache-dir -r requirements.lock; fi
COPY backend/ ./backend/
COPY --from=frontend /build/web/dist ./web/dist
RUN chmod -R a+rX /app && useradd --uid 1000 --create-home app && mkdir /data && chown app:app /data
USER app
ENV TRACEPAPER_DATA=/data PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:'+__import__('os').environ.get('PORT','8000')+'/api/health')"
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
