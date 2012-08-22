"""Hadoop Streaming jobs for building the term index at scale.

    hadoop jar hadoop-streaming.jar \\
        -input pages/*.jsonl -output index/ \\
        -mapper "python -m minicrawl.mapreduce.index_mapper" \\
        -reducer "python -m minicrawl.mapreduce.index_reducer"

`run_local` emulates the shuffle (sort by key) so the jobs can be tested without a cluster.
"""
from __future__ import annotations

import io
from typing import Callable, Iterable, TextIO


def run_local(mapper: Callable[[TextIO, TextIO], None], reducer: Callable[[TextIO, TextIO], None], lines: Iterable[str]) -> list[str]:
    map_in = io.StringIO("".join(line if line.endswith("\n") else line + "\n" for line in lines))
    map_out = io.StringIO()
    mapper(map_in, map_out)
    shuffled = sorted(map_out.getvalue().splitlines(), key=lambda l: l.split("\t", 1)[0])
    red_out = io.StringIO()
    reducer(io.StringIO("\n".join(shuffled) + ("\n" if shuffled else "")), red_out)
    return red_out.getvalue().splitlines()
