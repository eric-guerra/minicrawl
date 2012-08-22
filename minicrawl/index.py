"""Positional inverted index with BM25F-style field boosts, phrase queries, PageRank blending and snippets."""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .pagerank import pagerank
from .tokenizer import tokenize

# Terms in the title or headings count as multiple occurrences.
FIELD_WEIGHTS = {"title": 3, "headings": 2, "anchors": 2, "text": 1}
K1 = 1.2
B = 0.75
PAGERANK_WEIGHT = 0.3


@dataclass
class Hit:
    url: str
    title: str
    score: float
    snippet: str


class Index:
    def __init__(self):
        self.docs: list[dict] = []                         # {url, title, text, length}
        self.postings: dict[str, dict[int, float]] = {}    # term -> {doc: weighted tf}
        self.positions: dict[str, dict[int, list[int]]] = {}  # term -> {doc: positions in body}
        self.pagerank: dict[int, float] = {}
        self.avg_len = 0.0

    # ---------- building ----------

    @classmethod
    def build(cls, pages: Iterable[dict]) -> "Index":
        idx = cls()
        pages = list(pages)
        by_url = {p["url"]: i for i, p in enumerate(pages)}

        # Anchor text describes the *target* page, a strong relevance signal.
        anchors: dict[int, list[str]] = defaultdict(list)
        for p in pages:
            for link in p.get("links", []):
                target = by_url.get(link["url"])
                if target is not None and link.get("anchor"):
                    anchors[target].append(link["anchor"])

        postings: dict[str, dict[int, float]] = defaultdict(dict)
        positions: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
        total_len = 0
        for doc_id, p in enumerate(pages):
            fields = {
                "title": tokenize(p.get("title", "")),
                "headings": tokenize(" ".join(p.get("headings", []))),
                "anchors": tokenize(" ".join(anchors.get(doc_id, []))),
                "text": tokenize(p.get("text", "")),
            }
            length = 0.0
            for name, terms in fields.items():
                w = FIELD_WEIGHTS[name]
                length += w * len(terms)
                for t in terms:
                    postings[t][doc_id] = postings[t].get(doc_id, 0.0) + w
            for pos, t in enumerate(fields["text"]):
                positions[t][doc_id].append(pos)
            total_len += length
            idx.docs.append({"url": p["url"], "title": p.get("title") or p["url"], "text": p.get("text", ""), "length": length})

        idx.postings = dict(postings)
        idx.positions = {t: dict(d) for t, d in positions.items()}
        idx.avg_len = total_len / len(pages) if pages else 0.0

        ranks = pagerank({p["url"]: [l["url"] for l in p.get("links", [])] for p in pages})
        top = max(ranks.values(), default=1.0)
        idx.pagerank = {by_url[u]: r / top for u, r in ranks.items()}
        return idx

    # ---------- querying ----------

    def _idf(self, term: str) -> float:
        n = len(self.docs)
        df = len(self.postings.get(term, {}))
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def _bm25(self, terms: list[str]) -> dict[int, float]:
        scores: dict[int, float] = defaultdict(float)
        for term in set(terms):
            idf = self._idf(term)
            for doc_id, tf in self.postings.get(term, {}).items():
                norm = K1 * (1 - B + B * self.docs[doc_id]["length"] / (self.avg_len or 1))
                scores[doc_id] += idf * tf * (K1 + 1) / (tf + norm)
        return scores

    def _phrase_docs(self, phrase: list[str]) -> set[int]:
        if not phrase:
            return set()
        candidates = set(self.positions.get(phrase[0], {}))
        for t in phrase[1:]:
            candidates &= set(self.positions.get(t, {}))
        matches = set()
        for doc in candidates:
            starts = set(self.positions[phrase[0]][doc])
            for offset, t in enumerate(phrase[1:], start=1):
                starts &= {p - offset for p in self.positions[t][doc]}
                if not starts:
                    break
            if starts:
                matches.add(doc)
        return matches

    @staticmethod
    def parse_query(query: str) -> tuple[list[str], list[list[str]], set[str]]:
        """Supports "exact phrases" and -excluded terms. Returns (terms, phrases, excluded)."""
        phrases = [tokenize(p) for p in re.findall(r'"([^"]+)"', query)]
        rest = re.sub(r'"[^"]*"', " ", query)
        excluded = {t for w in re.findall(r"(?:^|\s)-(\S+)", rest) for t in tokenize(w)}
        rest = re.sub(r"(?:^|\s)-\S+", " ", rest)
        terms = tokenize(rest) + [t for p in phrases for t in p]
        return terms, [p for p in phrases if p], excluded

    def search(self, query: str, limit: int = 10) -> list[Hit]:
        terms, phrases, excluded = self.parse_query(query)
        if not terms:
            return []
        scores = self._bm25(terms)
        for phrase in phrases:
            allowed = self._phrase_docs(phrase)
            scores = {d: s for d, s in scores.items() if d in allowed}
        for t in excluded:
            for d in self.postings.get(t, {}):
                scores.pop(d, None)
        if not scores:
            return []

        best = max(scores.values())
        blended = {d: (1 - PAGERANK_WEIGHT) * s / best + PAGERANK_WEIGHT * self.pagerank.get(d, 0.0) for d, s in scores.items()}
        ranked = sorted(blended.items(), key=lambda kv: (-kv[1], self.docs[kv[0]]["url"]))[:limit]
        return [Hit(self.docs[d]["url"], self.docs[d]["title"], round(score, 4), self.snippet(d, terms)) for d, score in ranked]

    def snippet(self, doc_id: int, terms: list[str], width: int = 30) -> str:
        """The window of `width` words containing the most query terms."""
        words = self.docs[doc_id]["text"].split()
        if not words:
            return ""
        wanted = set(terms)
        stems = [tokenize(w, keep_stopwords=True) for w in words]
        hits = [1 if s and s[0] in wanted else 0 for s in stems]
        best_start, best = 0, -1
        window = sum(hits[:width])
        for start in range(0, max(1, len(words) - width + 1)):
            if start:
                window += (hits[start + width - 1] if start + width - 1 < len(hits) else 0) - hits[start - 1]
            if window > best:
                best, best_start = window, start
        chunk = words[best_start : best_start + width]
        out = " ".join(f"**{w}**" if s and s[0] in wanted else w for w, s in zip(chunk, stems[best_start : best_start + width]))
        prefix = "… " if best_start > 0 else ""
        suffix = " …" if best_start + width < len(words) else ""
        return prefix + out + suffix

    # ---------- persistence ----------

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({
                "docs": self.docs,
                "postings": {t: {str(d): tf for d, tf in p.items()} for t, p in self.postings.items()},
                "positions": {t: {str(d): pos for d, pos in p.items()} for t, p in self.positions.items()},
                "pagerank": {str(d): r for d, r in self.pagerank.items()},
                "avg_len": self.avg_len,
            }, fh)

    @classmethod
    def load(cls, path: str) -> "Index":
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        idx = cls()
        idx.docs = data["docs"]
        idx.postings = {t: {int(d): tf for d, tf in p.items()} for t, p in data["postings"].items()}
        idx.positions = {t: {int(d): pos for d, pos in p.items()} for t, p in data["positions"].items()}
        idx.pagerank = {int(d): r for d, r in data["pagerank"].items()}
        idx.avg_len = data["avg_len"]
        return idx
