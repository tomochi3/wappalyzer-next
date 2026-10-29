# pinned by digest; Dependabot proposes updates
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# dependencies are installed from requirements.txt, whose hashes pip checks
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt \
    && python -m playwright install --with-deps chromium

COPY . /tmp/wappalyzer-src
RUN pip install --no-cache-dir --no-deps /tmp/wappalyzer-src \
    && rm -rf /tmp/wappalyzer-src /tmp/requirements.txt

# Chromium renders untrusted pages, so never run it as root
RUN useradd --create-home --uid 1000 wappalyzer
USER wappalyzer
WORKDIR /app

ENTRYPOINT ["wappalyzer"]
