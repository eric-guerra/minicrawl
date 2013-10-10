"""URL normalization so the same page is only crawled once."""
from __future__ import annotations

from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlsplit, urlunsplit

DEFAULT_PORTS = {"http": 80, "https": 443}
# Query parameters that never change page content.
TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid", "sessionid"}
SKIP_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".pdf", ".zip", ".gz", ".mp3", ".mp4", ".css", ".js", ".ico", ".woff", ".woff2")


def normalize(url: str, base: str | None = None) -> str | None:
    """Resolve against base and canonicalize. Returns None for non-http(s) or unusable URLs."""
    if base is not None:
        url = urljoin(base, url)
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in DEFAULT_PORTS or not parts.hostname:
        return None

    host = parts.hostname.lower().rstrip(".")
    port = parts.port
    netloc = host if port in (None, DEFAULT_PORTS[scheme]) else f"{host}:{port}"

    path = _normalize_path(parts.path or "/")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS))
    return urlunsplit((scheme, netloc, path, query, ""))  # fragment dropped


def _normalize_path(path: str) -> str:
    segments: list[str] = []
    for seg in path.split("/"):
        if seg == "..":
            if segments:
                segments.pop()
        elif seg not in (".", ""):
            segments.append(quote(unquote(seg), safe="!$&'()*+,;=:@~-._"))
    normalized = "/" + "/".join(segments)
    if path.endswith("/") and normalized != "/":
        normalized += "/"
    return normalized


def host_of(url: str) -> str:
    return urlsplit(url).netloc


def is_crawlable(url: str) -> bool:
    return not urlsplit(url).path.lower().endswith(SKIP_EXTENSIONS)
