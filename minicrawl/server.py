"""Search UI and JSON API on the stdlib HTTP server."""
from __future__ import annotations

import html
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .index import Index

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>MiniCrawl</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{{font:15px/1.5 Arial,sans-serif;max-width:720px;margin:32px auto;padding:0 16px;color:#222}}
form{{display:flex;gap:8px}}input{{flex:1;padding:10px;font-size:16px}}button{{padding:10px 16px}}
.hit{{margin:20px 0}}.hit a{{font-size:18px;color:#1a0dab;text-decoration:none}}.url{{color:#006621;font-size:13px}}
.meta{{color:#777;font-size:13px}}</style></head><body>
<h1>MiniCrawl</h1><form><input name="q" value="{q}" autofocus placeholder='Try "exact phrase" or -exclude'><button>Search</button></form>
{results}</body></html>"""


def render_snippet(snippet: str) -> str:
    parts = html.escape(snippet).split("**")
    return "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(parts))


def make_handler(index: Index):
    class Handler(BaseHTTPRequestHandler):
        server_version = "MiniCrawl/1.0"

        def log_message(self, fmt, *args):  # quiet by default
            pass

        def _send(self, status: int, body: str, ctype: str) -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            parts = urlsplit(self.path)
            params = parse_qs(parts.query)
            q = params.get("q", [""])[0][:200]
            try:
                limit = max(1, min(50, int(params.get("limit", ["10"])[0])))
            except ValueError:
                limit = 10

            if parts.path == "/api/search":
                started = time.perf_counter()
                hits = index.search(q, limit) if q else []
                body = {"query": q, "took_ms": round((time.perf_counter() - started) * 1000, 2),
                        "results": [h.__dict__ for h in hits]}
                return self._send(200, json.dumps(body), "application/json")
            if parts.path == "/":
                results = ""
                if q:
                    hits = index.search(q, limit)
                    results = f'<p class="meta">{len(hits)} results from {len(index.docs)} pages</p>' + "".join(
                        f'<div class="hit"><a href="{html.escape(h.url)}">{html.escape(h.title)}</a>'
                        f'<div class="url">{html.escape(h.url)}</div><div>{render_snippet(h.snippet)}</div></div>'
                        for h in hits) or "<p>No results.</p>"
                return self._send(200, PAGE.format(q=html.escape(q), results=results), "text/html")
            self._send(404, "not found", "text/plain")

    return Handler


def serve(index: Index, host: str = "127.0.0.1", port: int = 8080) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(index))
