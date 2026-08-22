# ---- Stage 1: build the admin UI (Vue3 + Vite) ----
FROM node:20-alpine AS admin-ui
WORKDIR /ui
COPY client_admin/package.json ./
RUN npm install --no-audit --no-fund --ignore-scripts
COPY client_admin/ ./
RUN npm run build

# ---- Stage 2: API image (contains FFmpeg, runs non-root) ----
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=3000 \
    WEB_CONCURRENCY=2

# Use Tencent public mirrors so apt/pip downloads don't crawl from the default
# Debian/PyPI sources (ffmpeg install otherwise stalled ~1h on the cloud host).
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i \
            -e 's|http://deb.debian.org/debian|http://mirrors.tencent.com/debian|g' \
            -e 's|http://security.debian.org/debian-security|http://mirrors.tencent.com/debian-security|g' \
            -e 's|http://deb.debian.org/debian-security|http://mirrors.tencent.com/debian-security|g' \
            /etc/apt/sources.list.d/debian.sources; \
    fi

ENV PIP_INDEX_URL=https://mirrors.tencent.com/pypi/simple
ENV PIP_TRUSTED_HOST=mirrors.tencent.com

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin appuser

COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server/app ./app
# 管理端静态资源（Vite 构建产物，/admin 挂载）
COPY --from=admin-ui /ui/dist ./admin_dist

USER appuser
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '3000'), timeout=3).read()"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-3000} --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips='*'"]
