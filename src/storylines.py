"""Ongoing storylines for the World section.

A storyline is a story that runs for days or weeks (a war, an election, a
trade dispute). Each edition, the day's World stories are matched to the
storylines already on file. A match adds one dated line to that storyline.
When a story has appeared in earlier editions, its page shows "The story so
far": the last few dated lines, then today's.

The lines come from the stories' own summaries, written the day they ran, so
nothing here depends on the model remembering history. A storyline with no
update for RETENTION_DAYS is dropped.

State is only saved after an edition is actually sent (main.py), so a dry
run or a failed send changes nothing.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

import llm

STORYLINES_PATH = Path(__file__).parent.parent / "state" / "storylines.json"
RETENTION_DAYS = 21
MAX_UPDATES_KEPT = 10
EARLIER_SHOWN = 3  # how many earlier lines "The story so far" shows

# How much of the article the model sees per story.
TEXT_CHARS = 600


def load(today: str) -> list[dict]:
    """Load the storylines, dropping any with no update in RETENTION_DAYS."""
    if not STORYLINES_PATH.exists():
        return []
    stories = json.loads(STORYLINES_PATH.read_text())
    cutoff = (date.fromisoformat(today) - timedelta(days=RETENTION_DAYS)).isoformat()
    return [s for s in stories if s["updates"] and s["updates"][-1]["date"] >= cutoff]


def save(stories: list[dict]) -> None:
    STORYLINES_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORYLINES_PATH.write_text(json.dumps(stories, ensure_ascii=False, indent=2))


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _build_prompt(items: list[dict], stories: list[dict]) -> str:
    known = [
        {"id": s["id"], "name": s["name"], "latest": s["updates"][-1]["text"]}
        for s in stories
    ]
    todays = [
        {
            "story": i,
            "title": item["title"],
            "summary": item.get("summary", ""),
            "article_start": item.get("text", "")[:TEXT_CHARS],
        }
        for i, item in enumerate(items)
    ]
    return f"""You keep track of ongoing news storylines for a daily digest.

Storylines already on file:
{json.dumps(known, ensure_ascii=False, indent=1) if known else "(none yet)"}

Today's stories:
{json.dumps(todays, ensure_ascii=False, indent=1)}

For each of today's stories, decide:
- It continues a storyline on file: give that storyline's "id".
- It starts a new storyline: give a short "new_name" (2 to 4 words, for example \
"Israel election" or "US-China trade"). Only do this for a story that will \
plausibly make news again over the next days or weeks (a war, an election, a \
trade or legal fight, a major policy). Name the whole issue, not today's event.
- It is a one-off (an accident, a single announcement): give neither.

Also write "update": one plain sentence, 25 words at most, saying what is new \
in this story today. Take it only from the summary and article start above. \
Never invent a number, a name or a cause. Do not use double quote characters \
inside the sentence.

Respond with ONLY a JSON object, no other text: {{"stories": [{{"story": <number>, \
"id": <existing id or null>, "new_name": <name or null>, "update": "<sentence>"}}]}} \
with one element per story."""


def annotate(items: list[dict], stories: list[dict], today: str) -> None:
    """Match today's stories to storylines. Adds today's line to `stories`
    (in memory only; call save() to keep it) and sets item["storyline"] =
    {"name", "earlier": [{"date","text"}], "today"} on every story that has
    earlier lines to show."""
    if not items:
        return
    parsed = json.loads(llm.generate(_build_prompt(items, stories), json_mode=True, heavy=True))
    by_id = {s["id"]: s for s in stories}
    used: set[str] = set()
    for entry in parsed.get("stories", []):
        i, update = entry.get("story"), str(entry.get("update") or "").strip()
        if not isinstance(i, int) or not (0 <= i < len(items)) or not update:
            continue
        storyline = by_id.get(entry.get("id"))
        if storyline is None and entry.get("new_name"):
            new_id = _slug(str(entry["new_name"]))
            storyline = by_id.get(new_id)
            if storyline is None and new_id:
                storyline = {"id": new_id, "name": str(entry["new_name"]).strip(), "updates": []}
                stories.append(storyline)
                by_id[new_id] = storyline
        if storyline is None or storyline["id"] in used:
            continue
        used.add(storyline["id"])
        earlier = [u for u in storyline["updates"] if u["date"] < today]
        # A re-run on the same day replaces that day's line instead of doubling it.
        storyline["updates"] = earlier + [{"date": today, "text": update}]
        storyline["updates"] = storyline["updates"][-MAX_UPDATES_KEPT:]
        if earlier:
            items[i]["storyline"] = {
                "name": storyline["name"],
                "earlier": earlier[-EARLIER_SHOWN:],
                "today": update,
            }
