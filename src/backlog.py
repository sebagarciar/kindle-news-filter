"""Backlog and repeat handling. PRD 5.3.

Stores a fingerprint (normalised headline or URL), date, and one-line summary
for every item sent. Retained 7 days. A developing story should be reframed
as an update, not just suppressed — only skip when genuinely nothing changed.
"""

import json
from pathlib import Path

BACKLOG_PATH = Path(__file__).parent.parent / "state" / "backlog.json"
RETENTION_DAYS = 7


def load() -> list[dict]:
    """Load the backlog, pruned to the last 7 days."""
    raise NotImplementedError


def record(item: dict) -> None:
    """Append a sent item's fingerprint, date, and summary."""
    raise NotImplementedError


def find_match(candidate: dict, backlog: list[dict]) -> dict | None:
    """Return the matching backlog entry for a candidate, if any."""
    raise NotImplementedError
