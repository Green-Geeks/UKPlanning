FROM python:3.12-slim

WORKDIR /app

# Install system deps for lxml, psycopg2, and Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Install Playwright Chromium + system deps
RUN playwright install --with-deps chromium

COPY . .

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import os, httpx; httpx.get(f'http://localhost:{os.environ.get(\"APP_PORT\", \"8000\")}/', timeout=5)" || exit 1

CMD ["python", "run_server.py"]
