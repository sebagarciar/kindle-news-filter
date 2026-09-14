"""Preferences and exclusions. PRD 5.7.

preferences.txt: free-text steering, pasted directly into the ranking prompt.
Three write paths — edit the file directly, a "prefer ..." message to the
bot, or a message the bot's local classifier reads as soft steering.

exclusions.txt: hard filter (gossip, sport, royals, ...), applied before
ranking in two layers. Same three write paths, "no ..." / "exclude ..." on
the bot side.

  apply_exclusions         keyword match, pure Python, always runs
  apply_semantic_exclusions one model call per category, labels only

The second layer exists because most banned stories never say the banned
word: "no sport" has to remove "Real Madrid beats Barcelona", and no
keyword list gets there. The model is asked which headlines are about a
banned topic and nothing else — the dropping is still done here, in
Python. Telling the ranker to obey the ban as one instruction among five
was tried first and leaked 2 of 3 picks, which is why the judgement call
is isolated into its own yes/no question instead.

Both files are seeded from config/*.example.txt on first run — see _ensure_seeded.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import llm
import text_utils

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
    """Drop comment lines and trailing comments.

    Trailing matters for exclusions: every bot-written line carries an
    "# added <date>" stamp, and an exclusion term is matched literally, so
    a line read as "sport  # added 2026-09-13" would filter nothing.
    """
    cleaned = []
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if line:
            cleaned.append(line)
    return cleaned


def _stamp() -> str:
    return datetime.now(tz=timezone.utc).date().isoformat()


def load_preferences() -> str:
    _ensure_seeded(PREFERENCES_PATH, CONFIG_DIR / "preferences.example.txt")
    lines = _strip_comments(PREFERENCES_PATH.read_text().splitlines())
    return "\n".join(lines)


def append_preference(line: str) -> bool:
    """Add a soft steering line. False if it's already there, so the bot can
    say so instead of stacking duplicates."""
    _ensure_seeded(PREFERENCES_PATH, CONFIG_DIR / "preferences.example.txt")
    cleaned = line.strip()
    if not cleaned:
        return False
    if cleaned.lower() in [existing.lower() for existing in load_preferences().splitlines()]:
        return False
    with PREFERENCES_PATH.open("a") as f:
        f.write(f"{cleaned}  # added {_stamp()}\n")
    return True


def load_exclusions() -> list[str]:
    _ensure_seeded(EXCLUSIONS_PATH, CONFIG_DIR / "exclusions.example.txt")
    return [line.lower() for line in _strip_comments(EXCLUSIONS_PATH.read_text().splitlines())]


def append_exclusion(term: str) -> bool:
    """Add a term to the hard filter. False if it's already excluded."""
    _ensure_seeded(EXCLUSIONS_PATH, CONFIG_DIR / "exclusions.example.txt")
    cleaned = term.strip().lower()
    if not cleaned or cleaned in load_exclusions():
        return False
    with EXCLUSIONS_PATH.open("a") as f:
        f.write(f"{cleaned}  # added {_stamp()}\n")
    return True


def _matches(term: str, text: str) -> bool:
    """Word-prefix match: the term has to start a word, but may continue into
    one.

    A plain substring test was wrong in both directions. "sport" matched
    "tran|sport" and would have dropped every transport and infrastructure
    story the day that exclusion was added; meanwhile a term stored
    singular missed its own plural. Anchoring the front to a word boundary
    and letting the tail run kills the transport case and still catches
    sports, sporting and e-sports.
    """
    return re.search(rf"\b{re.escape(term)}\w*", text, re.IGNORECASE) is not None


def apply_exclusions(candidates: list[dict], exclusions: list[str]) -> list[dict]:
    """Deterministic hard filter, applied before any ranking call. A
    candidate is dropped if an excluded term appears in its title or summary."""
    if not exclusions:
        return candidates
    kept = []
    for candidate in candidates:
        text = f"{candidate['title']} {candidate.get('summary', '')}"
        if not any(_matches(term, text) for term in exclusions):
            kept.append(candidate)
    return kept


# One yes/no pass over a category's headlines, so a ban costs about one
# extra model call per category rather than one per candidate.
#
# Chunked, and with num_ctx set explicitly: a full RSS pool can be a
# hundred headlines, and Ollama's default context window silently
# truncates a prompt that long rather than erroring (see llm.py). A
# truncated list looks exactly like a model that decided nothing was
# banned, which is the one failure mode that must not pass silently.
# Smaller chunks than the title-only version used, because each entry now
# carries an excerpt as well.
_SEMANTIC_CHUNK = 20
_SEMANTIC_OPTIONS = {"temperature": 0, "num_predict": 400, "num_ctx": 8192}
_SEMANTIC_TIMEOUT = 120

# Excerpt per candidate. Enough to say what the story is about, short
# enough that 20 of them still fit the window above.
_SEMANTIC_EXCERPT_CHARS = 200


def _build_semantic_prompt(entries: list[dict], exclusions: list[str]) -> str:
    terms = "\n".join(f"- {term}" for term in exclusions)
    listing = "\n\n".join(
        f'{i}. {entry["title"]}' + (f'\n   {entry["excerpt"]}' if entry["excerpt"] else "")
        for i, entry in enumerate(entries, start=1)
    )
    return f"""The reader of a daily news digest has banned these topics outright:
{terms}

Below are numbered news items, each a headline and the opening of the \
article. Some are in Spanish. Decide, for each, whether the item is about \
any of those banned topics.

Judge the subject matter, not the wording. A match result, a transfer, a \
qualifying session, a league table, a rally stage or a squad announcement \
is sport even though the word "sport" never appears, and a palace tour or \
a succession story is royals even though the word "royal" never appears.

Being wrong in the other direction costs the reader a story they wanted, \
so do not flag an item on competitive language alone. "Win", "beat", \
"race", "title", "champion", "rival" and "lead" are everyday words in \
business, technology and politics: a company wanting to win a market, a \
race to ship a product, a party leading a poll and a firm taking the \
title of largest exporter are not sport. An item that merely mentions a \
banned topic while being about something else — a stadium financing \
scandal, an election held on a match day — is not about it either. The \
excerpt, not the headline's vocabulary, is what settles it.

Items:
{listing}

Respond with ONLY a JSON object, no other text: \
{{"banned": [{{"n": <item number>, "topic": "<which banned topic it is \
about, copied exactly from the list above>"}}]}}. Use an empty list if \
none of them are about a banned topic."""


def _flagged_index(flag: dict, chunk_size: int, exclusions: list[str]) -> int | None:
    """Validate one flag from the model, or None to ignore it.

    The model has to name which banned topic the item is about, copied from
    the list it was given. A flag naming a topic that isn't on the list is
    the model inventing a reason, so it doesn't get to drop a story.
    """
    if not isinstance(flag, dict):
        return None
    try:
        index = int(flag.get("n")) - 1
    except (TypeError, ValueError):
        return None
    if not 0 <= index < chunk_size:
        return None
    topic = str(flag.get("topic", "")).strip().lower()
    if topic not in exclusions:
        return None
    return index


def apply_semantic_exclusions(candidates: list[dict], exclusions: list[str]) -> list[dict]:
    """Second exclusion layer: drop candidates the local model identifies as
    being about a banned topic, even when they never name it.

    Raises if the model can't be reached or answers unusably, so the caller
    decides what a failure means. main.py keeps the candidates and puts the
    failure on the edition's status line: a missed exclusion is a bad
    edition, no edition at all is worse (PRD 5.10).
    """
    if not candidates or not exclusions:
        return candidates

    entries = [
        {
            "title": c["title"],
            "excerpt": text_utils.clean_text(c.get("summary", ""))[:_SEMANTIC_EXCERPT_CHARS],
        }
        for c in candidates
    ]

    banned_indices = set()
    for start in range(0, len(entries), _SEMANTIC_CHUNK):
        chunk = entries[start:start + _SEMANTIC_CHUNK]
        raw = llm.generate(
            _build_semantic_prompt(chunk, exclusions),
            json_mode=True,
            options=_SEMANTIC_OPTIONS,
            timeout=_SEMANTIC_TIMEOUT,
        )
        for flag in json.loads(raw)["banned"]:
            index = _flagged_index(flag, len(chunk), exclusions)
            if index is not None:
                banned_indices.add(start + index)

    return [c for i, c in enumerate(candidates) if i not in banned_indices]
