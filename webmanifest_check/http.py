"""Tiny polite HTTP client: GET only, size-capped, spaced requests."""

import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from . import USER_AGENT


@dataclass
class Response:
    url: str
    status: int = 0
    content_type: str = ""
    body: bytes = b""
    error: str = ""
    headers: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.error and 200 <= self.status < 300


class Fetcher:
    """GET with a User-Agent, a timeout, a body cap and a minimum gap between requests."""

    def __init__(self, delay: float = 1.0, timeout: float = 15.0, max_bytes: int = 5 * 1024 * 1024):
        self.delay = max(0.0, delay)
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.count = 0
        self._last = 0.0

    def get(self, url: str) -> Response:
        if not url.lower().startswith(("http://", "https://")):
            return Response(url, error="unsupported URL scheme")
        wait = self._last + self.delay - time.monotonic()
        if self._last and wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        self.count += 1
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body = r.read(self.max_bytes + 1)
                if len(body) > self.max_bytes:
                    return Response(r.geturl(), r.status, error="response too large")
                ctype = r.headers.get_content_type() if r.headers.get("Content-Type") else ""
                return Response(r.geturl(), r.status, ctype, body, headers=dict(r.headers))
        except urllib.error.HTTPError as e:
            ctype = e.headers.get_content_type() if e.headers and e.headers.get("Content-Type") else ""
            return Response(url, e.code, ctype, b"")
        except (urllib.error.URLError, OSError, ValueError) as e:
            reason = getattr(e, "reason", e)
            return Response(url, error=str(reason) or type(e).__name__)
