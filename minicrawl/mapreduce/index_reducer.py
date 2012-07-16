"""Reducer: groups sorted `term \\t url \\t tf` lines into `term \\t df \\t json-postings`."""
from __future__ import annotations

import json
import sys
from itertools import groupby
from typing import TextIO


def main(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> None:
    rows = (line.rstrip("\n").split("\t") for line in stdin if line.strip())
    for term, group in groupby(rows, key=lambda r: r[0]):
        postings: dict[str, int] = {}
        for _, url, tf in group:
            postings[url] = postings.get(url, 0) + int(tf)
        ordered = dict(sorted(postings.items(), key=lambda kv: (-kv[1], kv[0])))
        stdout.write(f"{term}\t{len(ordered)}\t{json.dumps(ordered, separators=(',', ':'))}\n")


if __name__ == "__main__":
    main()
