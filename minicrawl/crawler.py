"""Multi-threaded polite crawler that writes pages as JSON lines."""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from typing import Callable, Iterable

from .fetcher import Fetcher
from .frontier import Frontier
from .parser import parse_html
from .robots import RobotsCache
from .urls import host_of, is_crawlable, normalize

log = logging.getLogger("minicrawl")


@dataclass
class CrawlConfig:
    seeds: list[str]
    max_pages: int = 200
    max_depth: int = 3
    workers: int = 4
    delay: float = 1.0
    same_host_only: bool = True
    user_agent: str = "MiniCrawl"


@dataclass
class CrawlStats:
    fetched: int = 0
    indexed: int = 0
    skipped_robots: int = 0
    errors: int = 0
    duplicates: int = 0
    errors_by_url: dict[str, str] = field(default_factory=dict)


class Crawler:
    def __init__(self, config: CrawlConfig, fetcher: Fetcher | None = None, sink: Callable[[dict], None] | None = None):
        self.config = config
        self.fetcher = fetcher or Fetcher(user_agent=f"{config.user_agent}/1.0")
        self.robots = RobotsCache(self.fetcher, config.user_agent)
        self.frontier = Frontier(default_delay=config.delay)
        self.stats = CrawlStats()
        self.sink = sink or (lambda page: None)
        self._lock = threading.Lock()
        self._allowed_hosts = {host_of(u) for u in (normalize(s) for s in config.seeds) if u}

    def run(self) -> CrawlStats:
        for seed in self.config.seeds:
            url = normalize(seed)
            if url:
                self.frontier.add(url, 0)
        threads = [threading.Thread(target=self._work, name=f"crawl-{i}", daemon=True) for i in range(self.config.workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return self.stats

    def _budget_left(self) -> bool:
        with self._lock:
            return self.stats.fetched < self.config.max_pages

    def _work(self) -> None:
        while self._budget_left():
            item = self.frontier.next(timeout=max(5.0, self.config.delay * 3))
            if item is None:
                return
            url, depth = item
            try:
                self._process(url, depth)
            except Exception as e:  # a single bad page must never kill a worker
                log.exception("failed processing %s", url)
                with self._lock:
                    self.stats.errors += 1
                    self.stats.errors_by_url[url] = repr(e)
            finally:
                self.frontier.done()
        self.frontier.close()

    def _process(self, url: str, depth: int) -> None:
        if not self.robots.allowed(url):
            with self._lock:
                self.stats.skipped_robots += 1
            return
        delay = self.robots.crawl_delay(url)
        if delay is not None:
            self.frontier.set_host_delay(host_of(url), max(delay, self.config.delay))

        with self._lock:
            if self.stats.fetched >= self.config.max_pages:
                return
            self.stats.fetched += 1
        result = self.fetcher.fetch(url)
        if result.body is None:
            with self._lock:
                self.stats.errors += 1
                self.stats.errors_by_url[url] = result.error or f"HTTP {result.status}"
            return

        final = normalize(result.url) or url
        if final != url:
            if self.frontier.seen(final):
                with self._lock:
                    self.stats.duplicates += 1
                return
            self.frontier.mark_seen(final)

        page = parse_html(result.body, final)
        if page.canonical and page.canonical != final and self.frontier.seen(page.canonical):
            with self._lock:
                self.stats.duplicates += 1
            return

        if not page.noindex:
            self.sink({
                "url": final,
                "title": page.title,
                "text": page.text,
                "headings": page.headings,
                "links": [{"url": u, "anchor": a} for u, a in page.links],
                "depth": depth,
            })
            with self._lock:
                self.stats.indexed += 1

        if depth < self.config.max_depth:
            for link, _anchor in page.links:
                if not is_crawlable(link):
                    continue
                if self.config.same_host_only and host_of(link) not in self._allowed_hosts:
                    continue
                self.frontier.add(link, depth + 1)


def write_jsonl(path: str) -> tuple[Callable[[dict], None], Callable[[], None]]:
    """Thread-safe JSONL sink. Returns (sink, close)."""
    fh = open(path, "w", encoding="utf-8")
    lock = threading.Lock()

    def sink(page: dict) -> None:
        line = json.dumps(page, ensure_ascii=False)
        with lock:
            fh.write(line + "\n")

    return sink, fh.close


def read_jsonl(path: str) -> Iterable[dict]:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def stats_dict(stats: CrawlStats) -> dict:
    return asdict(stats)
