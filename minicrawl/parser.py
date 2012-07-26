"""Extracts title, visible text, links and robots directives from HTML."""
from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser

from .urls import normalize

SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "head"}
BLOCK_TAGS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "header", "footer"}


@dataclass
class ParsedPage:
    url: str
    title: str = ""
    text: str = ""
    headings: list[str] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)  # (url, anchor text)
    noindex: bool = False
    nofollow: bool = False
    canonical: str | None = None


class _Extractor(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.page = ParsedPage(url=base_url)
        self._skip_depth = 0
        self._in_title = False
        self._heading: list[str] | None = None
        self._anchor: tuple[str, list[str], bool] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "base" and a.get("href"):
            self.base_url = normalize(a["href"], self.base_url) or self.base_url
        if tag == "meta" and a.get("name", "").lower() == "robots":
            content = a.get("content", "").lower()
            self.page.noindex |= "noindex" in content
            self.page.nofollow |= "nofollow" in content
        if tag == "link" and "canonical" in a.get("rel", "").lower().split():
            self.page.canonical = normalize(a.get("href", ""), self.base_url)
        if tag == "title":
            self._in_title = True
        if tag in SKIP_TAGS and tag != "head":
            self._skip_depth += 1
        if tag in ("h1", "h2", "h3"):
            self._heading = []
        if tag == "a" and a.get("href"):
            target = normalize(a["href"], self.base_url)
            if target:
                self._anchor = (target, [], "nofollow" in a.get("rel", "").lower())
        if tag in BLOCK_TAGS:
            self._text.append(" ")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in SKIP_TAGS and tag != "head" and self._skip_depth:
            self._skip_depth -= 1
        if tag in ("h1", "h2", "h3") and self._heading is not None:
            text = " ".join("".join(self._heading).split())
            if text:
                self.page.headings.append(text)
            self._heading = None
        if tag == "a" and self._anchor:
            target, words, nofollow = self._anchor
            if not nofollow:
                self.page.links.append((target, " ".join("".join(words).split())))
            self._anchor = None
        if tag in BLOCK_TAGS:
            self._text.append(" ")

    def handle_data(self, data):
        if self._in_title:
            self.page.title += data
            return
        if self._skip_depth:
            return
        self._text.append(data)
        if self._heading is not None:
            self._heading.append(data)
        if self._anchor:
            self._anchor[1].append(data)

    def result(self) -> ParsedPage:
        self.page.title = " ".join(self.page.title.split())
        self.page.text = " ".join("".join(self._text).split())
        if self.page.nofollow:
            self.page.links = []
        # De-duplicate links, keeping the first anchor text seen.
        seen: dict[str, str] = {}
        for url, anchor in self.page.links:
            seen.setdefault(url, anchor)
        self.page.links = list(seen.items())
        return self.page


def parse_html(html: str, url: str) -> ParsedPage:
    extractor = _Extractor(url)
    extractor.feed(html)
    extractor.close()
    return extractor.result()
