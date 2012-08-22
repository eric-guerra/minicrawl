"""HTTP fetching with timeouts, size limits and content-type filtering (stdlib only)."""
from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass

MAX_BYTES = 2 * 1024 * 1024


@dataclass
class FetchResult:
    url: str              # final URL after redirects
    status: int
    content_type: str = ""
    body: str | None = None
    error: str | None = None


class Fetcher:
    def __init__(self, user_agent: str = "MiniCrawl/1.0 (+https://github.com/ericgyl817)", timeout: float = 10.0):
        self.user_agent = user_agent
        self.timeout = timeout

    def fetch(self, url: str, accept_any_type: bool = False) -> FetchResult:
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": "text/html,*/*;q=0.5"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                ctype = resp.headers.get("Content-Type", "")
                final_url = resp.geturl()
                if not accept_any_type and "html" not in ctype.lower():
                    return FetchResult(final_url, resp.status, ctype, None, "not html")
                raw = resp.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    return FetchResult(final_url, resp.status, ctype, None, "too large")
                charset = resp.headers.get_content_charset() or "utf-8"
                return FetchResult(final_url, resp.status, ctype, raw.decode(charset, errors="replace"))
        except urllib.error.HTTPError as e:
            return FetchResult(url, e.code, error=f"HTTP {e.code}")
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as e:
            return FetchResult(url, 0, error=str(getattr(e, "reason", e)))
