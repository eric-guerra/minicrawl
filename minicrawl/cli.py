"""Command line: crawl -> index -> search/serve."""
from __future__ import annotations

import argparse
import json
import logging
import sys

from .crawler import CrawlConfig, Crawler, read_jsonl, stats_dict, write_jsonl
from .index import Index
from .server import serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="minicrawl")
    sub = parser.add_subparsers(dest="command", required=True)

    c = sub.add_parser("crawl", help="crawl seed URLs into a JSONL file")
    c.add_argument("seeds", nargs="+")
    c.add_argument("-o", "--out", default="pages.jsonl")
    c.add_argument("--max-pages", type=int, default=200)
    c.add_argument("--max-depth", type=int, default=3)
    c.add_argument("--workers", type=int, default=4)
    c.add_argument("--delay", type=float, default=1.0, help="seconds between requests to one host")
    c.add_argument("--any-host", action="store_true", help="follow links off the seed hosts")

    i = sub.add_parser("index", help="build an index from crawled pages")
    i.add_argument("pages")
    i.add_argument("-o", "--out", default="index.json")

    s = sub.add_parser("search", help="query an index from the terminal")
    s.add_argument("index")
    s.add_argument("query")
    s.add_argument("-n", type=int, default=10)

    v = sub.add_parser("serve", help="run the search UI")
    v.add_argument("index")
    v.add_argument("--port", type=int, default=8080)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(threadName)s %(message)s")

    if args.command == "crawl":
        sink, close = write_jsonl(args.out)
        try:
            stats = Crawler(CrawlConfig(seeds=args.seeds, max_pages=args.max_pages, max_depth=args.max_depth,
                                        workers=args.workers, delay=args.delay, same_host_only=not args.any_host),
                            sink=sink).run()
        finally:
            close()
        print(json.dumps(stats_dict(stats), indent=2))
    elif args.command == "index":
        idx = Index.build(read_jsonl(args.pages))
        idx.save(args.out)
        print(f"indexed {len(idx.docs)} pages, {len(idx.postings)} terms -> {args.out}")
    elif args.command == "search":
        for n, hit in enumerate(Index.load(args.index).search(args.query, args.n), 1):
            print(f"{n:2}. {hit.title}  [{hit.score}]\n    {hit.url}\n    {hit.snippet}\n")
    elif args.command == "serve":
        server = serve(Index.load(args.index), port=args.port)
        print(f"serving on http://127.0.0.1:{args.port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
