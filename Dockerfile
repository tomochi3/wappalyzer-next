FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY . /tmp/wappalyzer-src

RUN pip install --no-cache-dir /tmp/wappalyzer-src \
    && python -m playwright install --with-deps chromium \
    && rm -rf /tmp/wappalyzer-src

# Chromium renders untrusted pages, so never run it as root
RUN useradd --create-home --uid 1000 wappalyzer
USER wappalyzer
WORKDIR /app

ENTRYPOINT ["wappalyzer"]
