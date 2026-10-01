FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app/scraper

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

# Match the data/raw and exports volumes mounted by docker-compose.yml.
ENV PATH="/app/scraper/.venv/bin:$PATH" \
    RAW_DATA_DIR=/app/data/raw \
    EXPORTS_DIR=/app/exports

CMD ["mbd", "worker"]
