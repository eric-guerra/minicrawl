import json
import threading
import urllib.request

from minicrawl.crawler import CrawlConfig, Crawler
from minicrawl.index import Index
from minicrawl.server import serve


def crawl(site, **overrides):
    base = f"http://127.0.0.1:{site.server_address[1]}/"
    pages = []
    config = CrawlConfig(seeds=[base], delay=0.0, workers=3, **overrides)
    stats = Crawler(config, sink=pages.append).run()
    return base, pages, stats


def test_crawls_site_respecting_robots_and_noindex(site):
    base, pages, stats = crawl(site)
    urls = {p["url"] for p in pages}
    assert urls == {base, base + "espresso", base + "pour-over", base + "deep"}  # /tea is noindex
    assert "/private/admin" not in site.hits                             # robots.txt
    assert "/logo.png" not in site.hits                                  # non-HTML extension
    # /deep is only linked from the noindex /tea page: links on noindex pages are still followed
    assert stats.skipped_robots == 1
    assert site.hits.count("/pour-over") == 1                            # tracking param normalized away


def test_depth_and_page_limits(site):
    _, pages, _ = crawl(site, max_depth=0)
    assert len(pages) == 1
    _, pages, stats = crawl(site, max_pages=2)
    assert stats.fetched == 2


def test_scripts_are_not_indexed(site):
    _, pages, _ = crawl(site)
    pour = next(p for p in pages if p["url"].endswith("pour-over"))
    assert "should not be indexed" not in pour["text"]


def test_end_to_end_search_and_http_api(site):
    _, pages, _ = crawl(site)
    index = Index.build(pages)
    hits = index.search("espresso machine")
    assert hits[0].title == "Espresso"
    assert "**espresso**" in hits[0].snippet.lower()

    server = serve(index, port=0)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        port = server.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/search?q=pour+over") as resp:
            body = json.load(resp)
        assert body["results"][0]["title"] == "Pour Over"
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/?q=%3Cscript%3E") as resp:
            assert b"<script>" not in resp.read().split(b"<body>")[1]
    finally:
        server.shutdown()
