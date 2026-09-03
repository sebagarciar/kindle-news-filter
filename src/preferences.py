"""Preferences and exclusions. PRD 5.7.

preferences.txt: free-text steering, pasted directly into the ranking prompt.
Two write paths — edit the file directly, or a "prefer ..." message to the bot.

exclusions.txt: hard filter (gossip, sport, royals, ...), applied
deterministically before ranking. Never left to the model's judgement.

Both files are seeded from config/*.example.txt on first run — see _ensure_seeded.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(__file__).parent.parent / "state"
CONFIG_DIR = Path(__file__).parent.parent / "config"
PREFERENCES_PATH = STATE_DIR / "preferences.txt"
EXCLUSIONS_PATH = STATE_DIR / "exclusions.txt"


def _ensure_seeded(state_path: Path, example_path: Path) -> None:
    if state_path.exists():
        return
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(example_path.read_text() if example_path.exists() else "")


def _strip_comments(lines: list[str]) -> list[str]:
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def load_preferences() -> str:
    _ensure_seeded(PREFERENCES_PATH, CONFIG_DIR / "preferences.example.txt")
    lines = _strip_comments(PREFERENCES_PATH.read_text().splitlines())
    return "\n".join(lines)


def append_preference(line: str) -> None:
    _ensure_seeded(PREFERENCES_PATH, CONFIG_DIR / "preferences.example.txt")
    stamp = datetime.now(tz=timezone.utc).date().isoformat()
    with PREFERENCES_PATH.open("a") as f:
        f.write(f"{line.strip()}  # added {stamp}\n")


def load_exclusions() -> list[str]:
    _ensure_seeded(EXCLUSIONS_PATH, CONFIG_DIR / "exclusions.example.txt")
    return [line.lower() for line in _strip_comments(EXCLUSIONS_PATH.read_text().splitlines())]


def apply_exclusions(candidates: list[dict], exclusions: list[str]) -> list[dict]:
    """Deterministic hard filter, applied before any ranking call. A
    candidate is dropped if an excluded term appears in its title or summary."""
    if not exclusions:
        return candidates
    kept = []
    for candidate in candidates:
        text = f"{candidate['title']} {candidate.get('summary', '')}".lower()
        if not any(term in text for term in exclusions):
            kept.append(candidate)
    return kept
