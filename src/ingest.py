"""RSS source ingestion. PRD 5.1.

Pulls 30-40 candidate headlines per category (world, ai, chile) via feedparser.
RSS feeds are reverse-chronological only — no popularity signal here, that
comes later from cross-source clustering in cluster.py.
"""

WORLD_FEEDS: list[str] = [
    # Reuters, BBC, AP, Guardian or similar — confirm URLs before use
]

AI_FEEDS: list[str] = [
    # mix of outlets, company blogs, HN front page filtered for AI topics
]

CHILE_FEEDS: list[str] = [
    # Emol, Cooperativa (by topic), BioBio. Verify La Tercera's RSS works.
]


def fetch_candidates(feed_urls: list[str]) -> list[dict]:
    """Fetch and normalise headlines from a list of RSS feed URLs."""
    raise NotImplementedError
