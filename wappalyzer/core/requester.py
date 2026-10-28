import sys
import time
from urllib.parse import urljoin, urlparse

import requests
import urllib3

from wappalyzer.core.security import NetworkPolicy, strip_control_chars

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_TIMEOUT = 30
MAX_REDIRECTS = 5
MAX_BODY_BYTES = 10 * 1024 * 1024

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "deflate",
    "DNT": "1",
    "Sec-GPC": "1",
    "Connection": "close",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Priority": "u=0, i",
    "TE": "trailers"
}


class BlockedRequest(requests.exceptions.RequestException):
    pass


class Fetcher:
    """HTTP client for one scan target.

    - every request has a timeout and a response size limit
    - TLS certificates are verified unless insecure=True
    - redirects are followed manually so every hop is checked against the
      network policy, and the cookie is only sent to the target's host
    """

    def __init__(self, target_url, cookie=None, timeout=DEFAULT_TIMEOUT, insecure=False):
        self.policy = NetworkPolicy(target_url)
        self.target_host = urlparse(target_url).hostname
        self.cookie = cookie
        self.timeout = timeout
        self.verify = not insecure

    def _read_body(self, response, deadline):
        chunks = []
        size = 0
        for chunk in response.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > MAX_BODY_BYTES:
                raise requests.exceptions.ContentDecodingError(
                    f"response larger than {MAX_BODY_BYTES} bytes: {response.url}"
                )
            if time.monotonic() > deadline:
                raise requests.exceptions.Timeout(f"response took longer than {self.timeout}s: {response.url}")
            chunks.append(chunk)
        response._content = b''.join(chunks)
        response._content_consumed = True

    def get(self, url, send_cookie=False):
        try:
            return self._get(url, send_cookie)
        except requests.exceptions.RequestException as e:
            print(strip_control_chars(e), file=sys.stderr)
            return None

    def _get(self, url, send_cookie):
        deadline = time.monotonic() + self.timeout
        history = []
        for _ in range(MAX_REDIRECTS + 1):
            if not self.policy.allows(url):
                raise BlockedRequest(f"blocked request to non-public address: {url}")
            headers = dict(HEADERS)
            if send_cookie and self.cookie and urlparse(url).hostname == self.target_host:
                headers['Cookie'] = self.cookie
            response = requests.get(
                url,
                headers=headers,
                verify=self.verify,
                timeout=self.timeout,
                allow_redirects=False,
                stream=True,
            )
            try:
                location = response.headers.get('Location')
                if response.is_redirect and location:
                    history.append(response)
                    url = urljoin(response.url, location)
                    continue
                self._read_body(response, deadline)
            finally:
                response.close()
            response.history = history
            return response
        raise requests.exceptions.TooManyRedirects(f"exceeded {MAX_REDIRECTS} redirects: {url}")
