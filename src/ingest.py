"""RSS source ingestion. PRD 5.1.

Pulls candidate headlines per category via feedparser. RSS feeds are
reverse-chronological only — no popularity signal here, that comes later
from cross-source clustering in cluster.py.

Every feed URL below was curl-verified live before being added. Two PRD
assumptions turned out to be wrong and are noted rather than silently
"fixed": Emol's RSS has been discontinued (every documented pattern
redirects to their plain HTML page), and Anthropic has no public RSS feed.
Both are dropped in favour of sources that actually return XML today.
"""

from __future__ import annotations

import re
from calendar import timegm
from datetime import datetime, timedelta, timezone

import feedparser

# How far back a feed entry can be and still count as a candidate. Generous
# enough to cover a slow feed or a missed run, but some source feeds (e.g.
# OpenAI's) return their entire history with no way to ask for "recent
# only" server-side, so this cutoff is what actually keeps the pool at the
# PRD's target of 30-40 candidates rather than thousands.
RECENCY_WINDOW = timedelta(hours=48)

# Applied per feed, not per category: a high-frequency outlet (BBC, say)
# would otherwise crowd out lower-frequency ones and defeat the point of
# cross-source clustering in cluster.py, which needs each source
# represented, not just the single loudest one.
MAX_PER_FEED = 10

WORLD_FEEDS: list[tuple[str, str]] = [
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("The Guardian World", "https://www.theguardian.com/world/rss"),
    ("NPR World", "https://feeds.npr.org/1004/rss.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
]

AI_FEEDS: list[tuple[str, str]] = [
    ("OpenAI", "https://openai.com/news/rss.xml"),
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
]

# Hacker News has no topic-filtered RSS, so the frontpage feed is pulled
# whole and filtered by keyword after parsing (see _is_ai_related).
HN_FRONTPAGE_FEED = ("Hacker News", "https://hnrss.org/frontpage")
_AI_KEYWORDS = re.compile(
    r"\b(ai|artificial intelligence|llm|gpt|openai|anthropic|claude|gemini|"
    r"chatgpt|machine learning|neural network|genai)\b",
    re.IGNORECASE,
)

# Cooperativa breaks feeds out by topic; "all" is used here to keep the
# candidate pool broad, matching what the ranking step is for.
CHILE_FEEDS: list[tuple[str, str]] = [
    ("Cooperativa", "https://www.cooperativa.cl/noticias/site/tax/port/all/rss____1.xml"),
    ("BioBioChile", "https://www.biobiochile.cl/static/feed-rss"),
    ("La Tercera", "https://www.latercera.com/rss"),
]


def _is_ai_related(entry) -> bool:
    text = f"{entry.get('title', '')} {entry.get('summary', '')}"
    return bool(_AI_KEYWORDS.search(text))


def _published_at(entry) -> datetime | None:
    struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if not struct:
        return None
    return datetime.fromtimestamp(timegm(struct), tz=timezone.utc)


def _normalise(entry, source: str, published_at: datetime | None) -> dict:
    return {
        "title": entry.get("title", "").strip(),
        "url": entry.get("link", ""),
        "source": source,
        "published": published_at.isoformat() if published_at else "",
        "summary": entry.get("summary", ""),
    }


def fetch_feed(source: str, url: str) -> list[dict]:
    """Fetch and normalise entries from one feed, dropping anything older
    than RECENCY_WINDOW. Entries with no parseable date are kept, since
    dropping them silently would be worse than an occasional undated item.

    Raises on total failure (bozo with no entries) so callers can record it
    as a source failure.
    """
    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"{source}: failed to parse feed ({parsed.bozo_exception})")
    cutoff = datetime.now(tz=timezone.utc) - RECENCY_WINDOW
    recent = []
    for entry in parsed.entries:
        published_at = _published_at(entry)
        if published_at and published_at < cutoff:
            continue
        recent.append((published_at, _normalise(entry, source, published_at)))
    # Undated entries sort last rather than being dropped outright.
    recent.sort(key=lambda pair: pair[0] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return [item for _, item in recent[:MAX_PER_FEED]]


def fetch_category(feeds: list[tuple[str, str]]) -> tuple[list[dict], list[str]]:
    """Fetch all feeds for a category. Returns (candidates, failed_source_names).

    A single dead feed must not take down the category — PRD 5.10 requires
    the edition to go out regardless, with failures surfaced as a status line.
    """
    candidates: list[dict] = []
    failed: list[str] = []
    for source, url in feeds:
        try:
            candidates.extend(fetch_feed(source, url))
        except Exception:
            failed.append(source)
    return candidates, failed


def fetch_ai_candidates() -> tuple[list[dict], list[str]]:
    """AI category candidates: the AI outlet feeds plus HN frontpage,
    keyword-filtered since HN has no topic-specific feed."""
    candidates, failed = fetch_category(AI_FEEDS)
    try:
        hn_entries = fetch_feed(*HN_FRONTPAGE_FEED)
        candidates.extend(e for e in hn_entries if _is_ai_related(e))
    except Exception:
        failed.append(HN_FRONTPAGE_FEED[0])
    return candidates, failed
