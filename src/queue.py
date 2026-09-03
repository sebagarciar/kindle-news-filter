"""Read-later queue. PRD 5.6.

FIFO, capped at 5 items per edition, oldest first. Remainder rolls over to
the next day rather than being dropped or forced in all at once.
"""

import json
from pathlib import Path

QUEUE_PATH = Path(__file__).parent.parent / "state" / "queue.json"
PER_EDITION_CAP = 5


def load() -> list[dict]:
    raise NotImplementedError


def add(item: dict) -> None:
    raise NotImplementedError


def pop_for_edition() -> list[dict]:
    """Remove and return up to PER_EDITION_CAP oldest items."""
    raise NotImplementedError
