"""Preferences and exclusions. PRD 5.7.

preferences.txt: free-text steering, pasted directly into the ranking prompt.
Two write paths — edit the file directly, or a "prefer ..." message to the bot.

exclusions.txt: hard filter (gossip, sport, royals, ...), applied
deterministically before ranking. Never left to the model's judgement.
"""

from pathlib import Path

STATE_DIR = Path(__file__).parent.parent / "state"
PREFERENCES_PATH = STATE_DIR / "preferences.txt"
EXCLUSIONS_PATH = STATE_DIR / "exclusions.txt"


def load_preferences() -> str:
    raise NotImplementedError


def append_preference(line: str) -> None:
    raise NotImplementedError


def load_exclusions() -> list[str]:
    raise NotImplementedError


def apply_exclusions(candidates: list[dict], exclusions: list[str]) -> list[dict]:
    """Deterministic hard filter, applied before any ranking call."""
    raise NotImplementedError
