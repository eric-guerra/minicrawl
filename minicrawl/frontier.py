"""Crawl frontier: breadth-first by depth with per-host politeness delays."""
from __future__ import annotations

import heapq
import itertools
import threading
import time
from dataclasses import dataclass, field

from .urls import host_of


@dataclass(order=True)
class _Entry:
    depth: int
    seq: int
    url: str = field(compare=False)


class Frontier:
    def __init__(self, default_delay: float = 1.0, clock=time.monotonic):
        self.default_delay = default_delay
        self.clock = clock
        self._heap: list[_Entry] = []
        self._seen: set[str] = set()
        self._next_allowed: dict[str, float] = {}
        self._host_delay: dict[str, float] = {}
        self._seq = itertools.count()
        self._lock = threading.Condition()
        self._in_flight = 0
        self._closed = False

    def add(self, url: str, depth: int) -> bool:
        with self._lock:
            if url in self._seen or self._closed:
                return False
            self._seen.add(url)
            heapq.heappush(self._heap, _Entry(depth, next(self._seq), url))
            self._lock.notify()
            return True

    def set_host_delay(self, host: str, delay: float) -> None:
        with self._lock:
            self._host_delay[host] = delay

    def seen(self, url: str) -> bool:
        with self._lock:
            return url in self._seen

    def mark_seen(self, url: str) -> None:
        with self._lock:
            self._seen.add(url)

    def next(self, timeout: float = 5.0) -> tuple[str, int] | None:
        """Shallowest URL whose host is ready; waits for politeness windows. None when exhausted."""
        deadline = self.clock() + timeout
        with self._lock:
            while True:
                if self._closed:
                    return None
                now = self.clock()
                ready_at = None
                skipped = []
                chosen = None
                while self._heap:
                    entry = heapq.heappop(self._heap)
                    host = host_of(entry.url)
                    allowed = self._next_allowed.get(host, 0.0)
                    if allowed <= now:
                        chosen = entry
                        self._next_allowed[host] = now + self._host_delay.get(host, self.default_delay)
                        break
                    skipped.append(entry)
                    ready_at = allowed if ready_at is None else min(ready_at, allowed)
                for e in skipped:
                    heapq.heappush(self._heap, e)
                if chosen:
                    self._in_flight += 1
                    return chosen.url, chosen.depth
                if not self._heap and self._in_flight == 0:
                    return None  # nothing queued and nobody can add more
                remaining = deadline - self.clock()
                if remaining <= 0:
                    return None
                wait = remaining if ready_at is None else min(remaining, max(0.0, ready_at - now))
                self._lock.wait(wait if wait > 0 else 0.001)

    def done(self) -> None:
        with self._lock:
            self._in_flight -= 1
            self._lock.notify_all()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._lock.notify_all()

    def __len__(self) -> int:
        with self._lock:
            return len(self._heap)
