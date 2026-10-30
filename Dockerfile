FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_CACHE_DIR=/tmp/uv-cache \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && useradd --system --uid 10001 --create-home --home-dir /home/app --shell /usr/sbin/nologin app \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN python -m pip install "uv==0.13.4" \
    && uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY data/competitor_catalogs ./data/competitor_catalogs

RUN uv sync --locked --no-dev \
    && uv cache clean \
    && mkdir -p /app/.rag_tender \
    && chown app:app /app/.rag_tender

USER app

EXPOSE 8000

CMD ["uvicorn", "nomenclature_matcher.api:app", "--host", "0.0.0.0", "--port", "8000"]
