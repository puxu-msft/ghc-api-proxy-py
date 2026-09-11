FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY . .

RUN python -m venv /opt/ghc-venv \
    && cp -a /app/.venv/lib/python3.14/site-packages/. /opt/ghc-venv/lib/python3.14/site-packages/ \
    && rm -rf /app/.venv \
    && rm -f /opt/ghc-venv/lib/python3.14/site-packages/_editable_impl_app.pth \
    && rm -f /opt/ghc-venv/lib/python3.14/site-packages/app-0.1.0.dist-info/RECORD \
    && rm -f /opt/ghc-venv/lib/python3.14/site-packages/app-0.1.0.dist-info/direct_url.json \
    && rm -f /opt/ghc-venv/lib/python3.14/site-packages/app-0.1.0.dist-info/uv_cache.json \
    && rm -f /opt/ghc-venv/lib/python3.14/site-packages/app-0.1.0.dist-info/uv_build.json

ENV VIRTUAL_ENV=/opt/ghc-venv \
    PATH="/opt/ghc-venv/bin:${PATH}" \
    PYTHONPATH="/app/src" \
    GHC_HOST=0.0.0.0 \
    GHC_PORT=4142 \
    GHC_UPSTREAM__TYPE=generic

EXPOSE 4142

CMD ["python", "-m", "app", "start"]
