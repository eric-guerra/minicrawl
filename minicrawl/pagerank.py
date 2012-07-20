"""PageRank by power iteration with dangling-node redistribution."""
from __future__ import annotations


def pagerank(links: dict[str, list[str]], damping: float = 0.85, tol: float = 1e-9, max_iter: int = 100) -> dict[str, float]:
    """`links` maps page -> outgoing pages. Targets outside the crawled set are ignored."""
    nodes = sorted(links)
    if not nodes:
        return {}
    index = {n: i for i, n in enumerate(nodes)}
    n = len(nodes)
    out = [[index[t] for t in set(links[src]) if t in index and t != src] for src in nodes]

    rank = [1.0 / n] * n
    for _ in range(max_iter):
        dangling = sum(rank[i] for i in range(n) if not out[i])
        base = (1 - damping) / n + damping * dangling / n
        new = [base] * n
        for i, targets in enumerate(out):
            if targets:
                share = damping * rank[i] / len(targets)
                for j in targets:
                    new[j] += share
        delta = sum(abs(a - b) for a, b in zip(new, rank))
        rank = new
        if delta < tol:
            break
    return {nodes[i]: rank[i] for i in range(n)}
