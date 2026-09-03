"""Cross-source clustering for World and AI. PRD 5.2.

Cross-source agreement is the importance proxy: a story covered by most
outlets in the pool is significant, one appearing in a single feed is
filler. Not used for Chile — the source pool there is too small for
clustering to carry real signal (rank.py passes Chile's full list straight
to the model instead).

Clustering is done with plain token-overlap similarity on headlines rather
than embeddings or a model call — this step runs on every candidate before
any ranking happens, so it needs to be fast, free, and dependency-light.
"""

from __future__ import annotations

import re

SIMILARITY_THRESHOLD = 0.4

_STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or",
    "is", "are", "was", "were", "be", "as", "by", "with", "from", "after",
    "over", "into", "amid", "its", "his", "her", "their", "says", "said",
}
_WORD_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9]+")


def _tokens(title: str) -> set[str]:
    words = _WORD_RE.findall(title.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def _similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    overlap = len(a & b)
    return overlap / min(len(a), len(b))


def cluster_by_similarity(candidates: list[dict]) -> list[list[dict]]:
    """Greedily group candidates into clusters by headline token overlap.

    Each candidate joins the first existing cluster it's similar enough to
    (comparing against that cluster's first/founding member); otherwise it
    starts a new cluster.
    """
    clusters: list[list[dict]] = []
    cluster_tokens: list[set[str]] = []

    for candidate in candidates:
        tokens = _tokens(candidate["title"])
        placed = False
        for i, founder_tokens in enumerate(cluster_tokens):
            if _similarity(tokens, founder_tokens) >= SIMILARITY_THRESHOLD:
                clusters[i].append(candidate)
                placed = True
                break
        if not placed:
            clusters.append([candidate])
            cluster_tokens.append(tokens)

    return clusters


def rank_clusters(clusters: list[list[dict]]) -> list[list[dict]]:
    """Rank clusters by distinct source count, then by most recent item."""

    def source_count(cluster: list[dict]) -> int:
        return len({item["source"] for item in cluster})

    def most_recent(cluster: list[dict]) -> str:
        dated = [item["published"] for item in cluster if item["published"]]
        return max(dated) if dated else ""

    return sorted(clusters, key=lambda c: (source_count(c), most_recent(c)), reverse=True)
