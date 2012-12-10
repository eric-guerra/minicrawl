# MiniCrawl

A polite multi-threaded **web crawler**, a **positional inverted index** with BM25 ranking blended with **PageRank**, a search UI and JSON API, and **Hadoop Streaming** jobs for building the term index at scale. Pure Python standard library.

> Portfolio reference implementation of a 2012 information-retrieval course project (originally Python + Hadoop + Lucene), rebuilt here with the core ranking pieces implemented from scratch.

## Pipeline

```
seeds ─▶ Frontier (BFS by depth, per-host delay) ─▶ worker threads ─▶ robots.txt check ─▶ fetch ─▶ parse
                                     ▲                                                          │
                                     └──────────── normalized, deduplicated links ◀─────────────┤
                                                                                                 ▼
                                                                                          pages.jsonl
                                                         ┌───────────────────────────────────────┤
                                                         ▼                                       ▼
                                          Index.build (in-process)            Hadoop Streaming mapper/reducer
                                          BM25F + positions + PageRank        term → df, postings
                                                         ▼
                                              search CLI · HTTP UI · /api/search
```

## Crawler

- URL canonicalization: scheme and host case, default ports, `.`/`..` segments, sorted query, tracking parameters (`utm_*`, `gclid`…) removed, fragments dropped
- robots.txt with a per-origin cache, `Crawl-delay`, and disallow-all on 401/403; `<meta name=robots content=noindex,nofollow>`; `rel=nofollow`; `rel=canonical` and redirect deduplication
- Politeness: at most one request per host per delay window; the shallowest URL is crawled first
- Limits on page count, depth, response size (2 MB) and content type; same-host scoping by default

## Ranking

- **BM25F-style** term weights: title ×3, headings ×2, inbound **anchor text** ×2, body ×1, with length normalization
- **Phrase queries** (`"pour over"`) checked against token positions; **exclusion** (`-tea`)
- **PageRank** by power iteration with dangling-mass redistribution, blended at 30% after normalizing BM25
- Snippets: the 30-word window containing the most query terms, with matches highlighted

## Usage

```bash
pip install -e .[test]
minicrawl crawl https://example.com --max-pages 200 --delay 1 -o pages.jsonl
minicrawl index pages.jsonl -o index.json
minicrawl search index.json '"french press" -decaf'
minicrawl serve index.json --port 8080
```

Hadoop:

```bash
hadoop jar hadoop-streaming.jar -input pages.jsonl -output terms \
  -mapper "python -m minicrawl.mapreduce.index_mapper" \
  -reducer "python -m minicrawl.mapreduce.index_reducer"
```

## Tests

```bash
pytest     # 22 tests; includes a full crawl of a local fixture site served over HTTP
```
