import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

SITE = {
    "/robots.txt": ("text/plain", "User-agent: *\nDisallow: /private/\n"),
    "/": ("text/html", """<html><head><title>Coffee Guide</title></head><body>
        <h1>Brewing coffee at home</h1>
        <p>Learn about espresso, pour over and french press brewing.</p>
        <a href="/espresso">Espresso machines</a> <a href="/pour-over?utm_source=x">Pour over</a>
        <a href="/private/admin">Admin</a> <a href="/logo.png">logo</a>
        <a href="https://elsewhere.example/">external</a></body></html>"""),
    "/espresso": ("text/html", """<html><head><title>Espresso</title></head><body>
        <h2>Pulling a shot</h2><p>Espresso needs finely ground beans and nine bars of pressure.
        A good espresso machine heats water to about 93 degrees.</p>
        <a href="/">Home</a> <a href="/pour-over">Pour over coffee</a> <a href="/tea">Tea</a></body></html>"""),
    "/pour-over": ("text/html", """<html><head><title>Pour Over</title>
        <link rel="canonical" href="/pour-over"></head><body>
        <p>Pour over brewing gives a clean cup. Use a gooseneck kettle and medium grind beans.</p>
        <script>var espresso = "should not be indexed";</script>
        <a href="/espresso">espresso</a> <a href="/">home</a></body></html>"""),
    "/tea": ("text/html", """<html><head><title>Tea</title><meta name="robots" content="noindex"></head>
        <body><p>Green tea and black tea.</p><a href="/deep">deeper</a></body></html>"""),
    "/deep": ("text/html", "<html><head><title>Deep</title></head><body><p>very deep page</p></body></html>"),
    "/private/admin": ("text/html", "<html><body>secret</body></html>"),
}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        self.server.hits.append(path)
        if path not in SITE:
            self.send_response(404)
            self.end_headers()
            return
        ctype, body = SITE[path]
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def site():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.hits = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
