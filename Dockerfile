FROM python:3.12-slim

ARG BUILD_VERSION=dev

LABEL org.opencontainers.image.title="CCTV Viewer" \
      org.opencontainers.image.description="Timeline viewer for CCTV recordings" \
      org.opencontainers.image.version="${BUILD_VERSION}" \
      org.opencontainers.image.source="https://github.com/robertoamd90/cctv-timeline-viewer"

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ctv_server ./ctv_server
COPY ctv_web ./ctv_web
RUN test -f /app/ctv_server/main.py

RUN mkdir -p /root/.ctv /data

ENV CTV_DB=/root/.ctv/ctv.db
ENV CTV_THUMBNAILS=/root/.ctv/thumbnails
ENV PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]

CMD ["python", "-m", "uvicorn", "ctv_server.main:app", "--app-dir", "/app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
