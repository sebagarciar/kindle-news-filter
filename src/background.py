"""The three-line "Background" block under each World and AI story.

Runs after the full article has been fetched, because the article text is
what the lines are written from. One model call per story. Any failure
leaves the story without a block and adds a line to the status line; the
edition still goes out.
"""

from __future__ import annotations

import json

import llm
import text_utils

# How much of the article the model reads. Enough for the full piece in
# almost every case; the fetch step already caps articles near this size.
ARTICLE_CHARS = 8000

# How much of an analysis piece's RSS excerpt the model sees.
ANALYSIS_EXCERPT_CHARS = 400

_LANGUAGE_NAME = {"en": "English", "es": "Spanish"}

_KEYS = ("what_happened", "how_we_got_here", "what_to_watch")


def _build_prompt(item: dict, language: str) -> str:
    analysis = item.get("analysis")
    analysis_block = (
        f'\nRelated analysis, from {analysis["source"]}: "{analysis["title"]}"\n{analysis["excerpt"]}\n'
        if analysis else ""
    )
    lang_name = _LANGUAGE_NAME[language]
    return f"""You write a three-line "Background" box for one news story in a daily \
digest. The reader is smart but not an expert, and wants the global context, \
not more detail from the article.

Headline: {item["title"]}

Article:
{item["text"][:ARTICLE_CHARS]}
{analysis_block}
Write exactly three lines in {lang_name}, one plain sentence each, no more than 30 words each:
- what_happened: the single fact that matters, in plain words.
- how_we_got_here: the earlier events or trend that explain why this is happening now.
- what_to_watch: the next thing that will show where this is going.

Rules:
- Take facts from the article and any related analysis first. You may add widely known background, but only \
when you are sure of it. Never invent a number, a date, a name or a cause. If you \
are not sure, say less.
- Say who people are, and what role they hold, only as the article says. Never guess a role or a relationship.
- Do not repeat the headline.
- Plain, short words. No jargon, no hype.
- Do not use double quote characters inside a line; use single quotes if you must.

Respond with ONLY a JSON object, no other text:
{{"what_happened": "...", "how_we_got_here": "...", "what_to_watch": "..."}}"""


def write_background(item: dict, language: str = "en") -> dict | None:
    """Return {"what_happened", "how_we_got_here", "what_to_watch"} or None
    when the article has no real text to work from."""
    if not item.get("text") or len(item["text"]) < 400:
        return None
    # One retry: now and then the model returns JSON that does not parse, or
    # leaves a line empty.
    for attempt in (1, 2):
        try:
            parsed = json.loads(llm.generate(_build_prompt(item, language), json_mode=True, heavy=True))
            block = {key: str(parsed.get(key, "")).strip() for key in _KEYS}
            if not all(block.values()):
                raise ValueError("model left a line empty")
            break
        except ValueError:
            if attempt == 2:
                raise
    block["lang"] = language
    return block


def add_background(items: list[dict], failures: list[str], label: str, language: str = "en") -> None:
    """Attach item["background"] to each item in place."""
    for item in items:
        try:
            block = write_background(item, language)
        except Exception as e:
            failures.append(f"{label}: background failed for '{item['title'][:40]}' ({e})")
            continue
        if block:
            item["background"] = block


def _match_prompt(items: list[dict], pieces: list[dict]) -> str:
    stories = [{"story": i, "title": item["title"]} for i, item in enumerate(items)]
    listed = [
        {
            "piece": i,
            "source": p["source"],
            "title": p["title"],
            "excerpt": text_utils.clean_text(p.get("summary", ""))[:ANALYSIS_EXCERPT_CHARS],
        }
        for i, p in enumerate(pieces)
    ]
    return f"""Below are today's news stories and a list of recent analysis pieces. \
For each story, pick the one analysis piece that best explains the story or the \
bigger issue behind it. Only pick a piece that is clearly about the same story or \
the same underlying issue. If none fits, use null. Do not reuse a piece for two stories.

Stories:
{json.dumps(stories, ensure_ascii=False, indent=1)}

Analysis pieces:
{json.dumps(listed, ensure_ascii=False, indent=1)}

Respond with ONLY a JSON object, no other text: {{"matches": [{{"story": <number>, \
"piece": <number or null>}}]}} with one element per story."""


def match_analysis(items: list[dict], pieces: list[dict]) -> None:
    """Attach item["analysis"] = {title, url, source, excerpt} in place, for
    each story that has a matching analysis piece. One model call."""
    if not items or not pieces:
        return
    parsed = json.loads(llm.generate(_match_prompt(items, pieces), json_mode=True, heavy=True))
    used: set[int] = set()
    for match in parsed.get("matches", []):
        story, piece = match.get("story"), match.get("piece")
        if not isinstance(story, int) or not isinstance(piece, int):
            continue
        if not (0 <= story < len(items)) or not (0 <= piece < len(pieces)) or piece in used:
            continue
        used.add(piece)
        chosen = pieces[piece]
        items[story]["analysis"] = {
            "title": chosen["title"],
            "url": chosen["url"],
            "source": chosen["source"],
            "excerpt": text_utils.clean_text(chosen.get("summary", ""))[:ANALYSIS_EXCERPT_CHARS],
        }
