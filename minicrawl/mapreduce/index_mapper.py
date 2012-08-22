"""Mapper: page JSON line -> `term \\t url \\t tf` for every term on the page."""
from __future__ import annotations

import json
import sys
from collections import Counter
from typing import TextIO

from ..tokenizer import tokenize


def main(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> None:
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            page = json.loads(line)
        except json.JSONDecodeError:
            sys.stderr.write("reporter:counter:minicrawl,bad_json,1\n")
            continue
        counts = Counter(tokenize(page.get("title", "") + " " + page.get("text", "")))
        url = page["url"].replace("\t", "%09")
        for term, tf in counts.items():
            stdout.write(f"{term}\t{url}\t{tf}\n")


if __name__ == "__main__":
    main()
