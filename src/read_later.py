"""Read-later queue. PRD 5.6.

FIFO, capped at 5 items per edition, oldest first. The remainder rolls over
to the next day rather than being dropped or forced in all at once.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

QUEUE_PATH = Path(__file__).parent.parent / "state" / "queue.json"
PER_EDITION_CAP = 5


def load() -> list[dict]:
    if not QUEUE_PATH.exists():
        return []
    return json.loads(QUEUE_PATH.read_text())


def _save(items: list[dict]) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2))


def add(item: dict) -> None:
    """item needs 'url' (may be empty for a plain-text note) and 'text'."""
    items = load()
    items.append({
        "url": item.get("url", ""),
        "text": item.get("text", ""),
        "added_at": datetime.now(tz=timezone.utc).isoformat(),
    })
    _save(items)


def pop_for_edition() -> list[dict]:
    """Remove and return up to PER_EDITION_CAP oldest items; the rest stays queued."""
    items = load()
    taken, remaining = items[:PER_EDITION_CAP], items[PER_EDITION_CAP:]
    _save(remaining)
    return taken
