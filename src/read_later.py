"""Read-later queue. PRD 5.6, hardened after the 2026-09-04 edition.

FIFO, capped at 5 items per edition, oldest first. The remainder rolls over
to the next day rather than being dropped or forced in all at once.

Picking items for an edition no longer removes them. The first version
deleted them at pick time, before the EPUB was even built, and on
2026-09-04 the pipeline was re-run twice after the first send: the queued
video had already been consumed by the first run, so both later editions —
including the copy saved to output/ — went out without it, with nothing
left on disk to rebuild it from. A crash between pick and send would have
lost it the same way.

So: picking is read-only, the delivery stamp is written only once the send
has actually succeeded, and a re-run on the same day picks the same items
again and rebuilds an identical Read Later section. Delivered items are
pruned once they pass RETENTION_DAYS, which is what keeps the file bounded
now that nothing deletes on read.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

QUEUE_PATH = Path(__file__).parent.parent / "state" / "queue.json"
PER_EDITION_CAP = 5
RETENTION_DAYS = 7


def _normalize(item: dict) -> dict:
    """Fill in fields added after the first version of the queue file, so an
    older queue.json still loads."""
    return {
        "id": item.get("id") or uuid.uuid4().hex,
        "url": item.get("url", ""),
        "text": item.get("text", ""),
        "added_at": item.get("added_at", ""),
        "delivered_on": item.get("delivered_on"),
    }


def load() -> list[dict]:
    if not QUEUE_PATH.exists():
        return []
    return [_normalize(item) for item in json.loads(QUEUE_PATH.read_text())]


def _save(items: list[dict]) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2))


def add(item: dict) -> None:
    """item needs 'url' (may be empty for a plain-text note) and 'text'."""
    items = load()
    items.append(_normalize({
        "url": item.get("url", ""),
        "text": item.get("text", ""),
        "added_at": datetime.now(tz=timezone.utc).isoformat(),
    }))
    _save(items)


def take_for_edition(edition_date: str) -> list[dict]:
    """Up to PER_EDITION_CAP oldest items for this edition, leaving the queue
    untouched.

    Items never delivered qualify, and so do items already delivered on this
    same date — that second case is what makes a re-run of today's edition
    carry exactly what the first run carried, instead of an empty section.
    """
    eligible = [item for item in load() if item["delivered_on"] in (None, edition_date)]
    return eligible[:PER_EDITION_CAP]


def mark_delivered(items: list[dict], edition_date: str) -> None:
    """Stamp the items an edition actually shipped, then drop the ones whose
    retention window has passed. Call this only after delivery succeeds."""
    delivered_ids = {item["id"] for item in items}
    cutoff = (date.fromisoformat(edition_date) - timedelta(days=RETENTION_DAYS)).isoformat()

    kept = []
    for item in load():
        if item["id"] in delivered_ids:
            item["delivered_on"] = edition_date
        if item["delivered_on"] is None or item["delivered_on"] > cutoff:
            kept.append(item)
    _save(kept)
