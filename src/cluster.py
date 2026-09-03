"""Cross-source clustering for World and AI. PRD 5.2.

Cross-source agreement is the importance proxy: a story covered by most
outlets in the pool is significant, one appearing in a single feed is filler.
Not used for Chile — the source pool there is too small for clustering to
carry real signal (see rank.py).
"""


def cluster_by_similarity(candidates: list[dict]) -> list[list[dict]]:
    """Group candidate headlines into clusters by similarity."""
    raise NotImplementedError


def rank_clusters(clusters: list[list[dict]]) -> list[list[dict]]:
    """Rank clusters by source count, then recency."""
    raise NotImplementedError
