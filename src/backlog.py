"""Backlog and repeat handling. PRD 5.3.

Stores a fingerprint (normalised headline), date, and one-line summary for
every item sent. Retained 7 days. A developing story should be reframed as
an update, not just suppressed — find_match() only identifies the overlap;
rank.py decides (via the model) whether to skip or reframe it.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKLOG_PATH = Path(__file__).parent.parent / "state" / "backlog.json"
RETENTION_DAYS = 7
_MATCH_THRESHOLD = 0.5
_WORD_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9]+")


def fingerprint(title: str) -> str:
    """Normalised headline: lowercase, stripped of punctuation and stopwords,
    used for matching a candidate against past editions."""
    words = _WORD_RE.findall(title.lower())
    return " ".join(sorted(words))


def load() -> list[dict]:
    """Load the backlog, pruned to the last RETENTION_DAYS days."""
    if not BACKLOG_PATH.exists():
        return []
    entries = json.loads(BACKLOG_PATH.read_text())
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=RETENTION_DAYS)
    return [e for e in entries if datetime.fromisoformat(e["date"]) >= cutoff]


def record(item: dict) -> None:
    """Append a sent item's fingerprint, date, and summary. item needs
    'title', 'summary', and 'url'."""
    entries = load()
    entries.append({
        "fingerprint": fingerprint(item["title"]),
        "url": item.get("url", ""),
        "date": datetime.now(tz=timezone.utc).isoformat(),
        "title": item["title"],
        "summary": item["summary"],
    })
    BACKLOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    BACKLOG_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2))


def find_match(candidate: dict, backlog: list[dict]) -> dict | None:
    """Return the matching backlog entry for a candidate, if any — same URL,
    or a token-overlap match on the normalised headline."""
    if not backlog:
        return None
    if candidate.get("url"):
        for entry in backlog:
            if entry.get("url") and entry["url"] == candidate["url"]:
                return entry
    candidate_tokens = set(fingerprint(candidate["title"]).split())
    if not candidate_tokens:
        return None
    best, best_score = None, 0.0
    for entry in backlog:
        entry_tokens = set(entry["fingerprint"].split())
        if not entry_tokens:
            continue
        overlap = len(candidate_tokens & entry_tokens) / min(len(candidate_tokens), len(entry_tokens))
        if overlap > best_score:
            best, best_score = entry, overlap
    return best if best_score >= _MATCH_THRESHOLD else None
