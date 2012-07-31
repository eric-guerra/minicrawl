"""Per-host robots.txt cache built on urllib.robotparser."""
from __future__ import annotations

import threading
import time
from urllib.robotparser import RobotFileParser
from urllib.parse import urlsplit

from .fetcher import Fetcher


class RobotsCache:
    def __init__(self, fetcher: Fetcher, user_agent: str, ttl_seconds: float = 3600):
        self.fetcher = fetcher
        self.user_agent = user_agent
        self.ttl = ttl_seconds
        self._cache: dict[str, tuple[float, RobotFileParser]] = {}
        self._lock = threading.Lock()

    def _parser_for(self, url: str) -> RobotFileParser:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        with self._lock:
            hit = self._cache.get(origin)
            if hit and time.monotonic() - hit[0] < self.ttl:
                return hit[1]

        rp = RobotFileParser()
        result = self.fetcher.fetch(origin + "/robots.txt", accept_any_type=True)
        if result.status == 200 and result.body is not None:
            rp.parse(result.body.splitlines())
        elif result.status in (401, 403):
            rp.disallow_all = True  # per RFC 9309, treat auth-required robots as disallow-all
        else:
            rp.allow_all = True  # missing robots.txt means everything is allowed
        with self._lock:
            self._cache[origin] = (time.monotonic(), rp)
        return rp

    def allowed(self, url: str) -> bool:
        return self._parser_for(url).can_fetch(self.user_agent, url)

    def crawl_delay(self, url: str) -> float | None:
        delay = self._parser_for(url).crawl_delay(self.user_agent)
        return float(delay) if delay is not None else None
