"""Tokenization and light stemming shared by indexing and querying."""
from __future__ import annotations

import re

TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")

STOPWORDS = frozenset(
    """a an and are as at be but by for from has have he her his i if in into is it its of on or our
    she so than that the their them then there these they this to was we were what when which who will
    with you your""".split()
)


def stem(word: str) -> str:
    """A small suffix-stripping stemmer (a subset of Porter step 1) good enough for English search."""
    if len(word) <= 3 or word.isdigit():
        return word
    for suffix, replacement in (("sses", "ss"), ("ies", "y"), ("ss", "ss"), ("s", "")):
        if word.endswith(suffix):
            word = word[: len(word) - len(suffix)] + replacement
            break
    for suffix in ("ingly", "edly", "ing", "ed"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3 and re.search(r"[aeiouy]", word[: -len(suffix)]):
            word = word[: -len(suffix)]
            if word.endswith(("at", "bl", "iz")):
                word += "e"
            elif len(word) > 2 and word[-1] == word[-2] and word[-1] not in "lsz":
                word = word[:-1]
            break
    return word


def tokenize(text: str, keep_stopwords: bool = False) -> list[str]:
    """Returns stemmed terms in order (positions matter for phrase queries)."""
    out = []
    for raw in TOKEN_RE.findall(text.lower()):
        raw = raw.replace("'", "")
        if not keep_stopwords and raw in STOPWORDS:
            continue
        out.append(stem(raw))
    return out
