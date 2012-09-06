import pytest

from minicrawl.frontier import Frontier
from minicrawl.index import Index
from minicrawl.mapreduce import index_mapper, index_reducer, run_local
from minicrawl.pagerank import pagerank
from minicrawl.parser import parse_html
from minicrawl.tokenizer import stem, tokenize
from minicrawl.urls import is_crawlable, normalize


@pytest.mark.parametrize("raw,expected", [
    ("HTTP://Example.COM:80/a/./b/../c?b=2&a=1#frag", "http://example.com/a/c?a=1&b=2"),
    ("https://example.com:443", "https://example.com/"),
    ("https://example.com:8443/x/", "https://example.com:8443/x/"),
    ("https://example.com/?utm_source=tw&id=5", "https://example.com/?id=5"),
    ("https://example.com/a%20b", "https://example.com/a%20b"),
    ("mailto:someone@example.com", None),
    ("javascript:void(0)", None),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


def test_normalize_resolves_relative():
    assert normalize("../img/x?y=1", "https://a.com/docs/guide/") == "https://a.com/docs/img/x?y=1"
    assert is_crawlable("https://a.com/page") and not is_crawlable("https://a.com/file.PDF")


def test_parser_extracts_fields():
    page = parse_html("""<html><head><title> Hello  World </title><base href="https://x.com/sub/"></head>
        <body><h1>Main <em>heading</em></h1><p>Body&nbsp;text</p><style>.x{}</style>
        <a href="a">first</a><a href="a">dupe</a><a href="b" rel="nofollow">skip</a></body></html>""", "https://x.com/")
    assert page.title == "Hello World"
    assert page.headings == ["Main heading"]
    assert "Body" in page.text and ".x" not in page.text
    assert page.links == [("https://x.com/sub/a", "first")]


def test_meta_nofollow_drops_links():
    page = parse_html('<meta name="robots" content="noindex, nofollow"><a href="/x">x</a>', "https://x.com/")
    assert page.noindex and page.nofollow and page.links == []


def test_tokenizer_and_stemmer():
    assert tokenize("The Cats are RUNNING to the caresses!") == ["cat", "run", "caress"]
    assert [stem(w) for w in ("ponies", "hopping", "running", "brewed", "brewing", "coffee")] ==         ["pony", "hop", "run", "brew", "brew", "coffee"]


DOCS = [
    {"url": "u:a", "title": "Espresso basics", "text": "espresso is concentrated coffee brewed under pressure",
     "links": [{"url": "u:b", "anchor": "pour over guide"}]},
    {"url": "u:b", "title": "Brewing", "text": "pour over coffee is brewed by hand; espresso is not",
     "links": [{"url": "u:a", "anchor": "espresso"}]},
    {"url": "u:c", "title": "Tea", "text": "green tea is not coffee over and over", "links": [{"url": "u:a", "anchor": ""}]},
]


def test_bm25_prefers_title_matches():
    hits = Index.build(DOCS).search("espresso")
    assert [h.url for h in hits][:2] == ["u:a", "u:b"]


def test_phrase_and_exclusion():
    idx = Index.build(DOCS)
    assert [h.url for h in idx.search('"pour over"')] == ["u:b"]
    assert "u:c" not in [h.url for h in idx.search("coffee -tea")]
    assert idx.search("") == [] and idx.search("the and of") == []


def test_anchor_text_counts_for_target():
    # "guide" only appears in the anchor pointing to u:b.
    assert [h.url for h in Index.build(DOCS).search("guide")] == ["u:b"]


def test_index_round_trip(tmp_path):
    idx = Index.build(DOCS)
    path = tmp_path / "index.json"
    idx.save(str(path))
    assert [h.url for h in Index.load(str(path)).search("coffee")] == [h.url for h in idx.search("coffee")]


def test_pagerank_properties():
    ranks = pagerank({"a": ["b"], "b": ["c"], "c": ["a"], "d": ["a"], "e": []})
    assert sum(ranks.values()) == pytest.approx(1.0)
    assert ranks["a"] > ranks["d"]
    assert ranks["d"] == pytest.approx(ranks["e"])
    assert pagerank({}) == {}


def test_frontier_breadth_first_and_politeness():
    clock = [0.0]
    f = Frontier(default_delay=10.0, clock=lambda: clock[0])
    f.add("http://a/1", 1)
    f.add("http://a/0", 0)
    f.add("http://b/0", 0)
    assert not f.add("http://a/0", 0)
    assert f.next(timeout=0) == ("http://a/0", 0)
    assert f.next(timeout=0) == ("http://b/0", 0)
    assert f.next(timeout=0) is None  # host a is still cooling down
    clock[0] = 11
    assert f.next(timeout=0) == ("http://a/1", 1)


def test_mapreduce_matches_in_process_counts():
    import json
    lines = [json.dumps(d) for d in DOCS] + ["not json"]
    out = run_local(index_mapper.main, index_reducer.main, lines)
    table = {line.split("\t")[0]: (int(line.split("\t")[1]), json.loads(line.split("\t")[2])) for line in out}
    assert table["coffee"][0] == 3
    assert table["espresso"][1] == {"u:a": 2, "u:b": 1}
