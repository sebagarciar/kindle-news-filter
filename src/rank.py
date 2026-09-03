"""Final selection via a local model. PRD 5.2, 5.3.

For World and AI, input is pre-ranked clusters (cluster.py) — one candidate
per cluster (the most recent) is passed through, tagged with how many
sources covered it. For Chile, the full candidate list goes straight in —
no clustering, the source pool is too small for it to mean anything.

Every category's call takes three inputs: the candidates, the preferences
file (5.7), and the 7-day backlog (5.3). Backlog matching is done
deterministically in Python (backlog.find_match) rather than handed to the
model raw; matched candidates carry their prior summary so the model can
decide to skip (nothing new) or reframe as an update (PRD 5.3 prefers
reframing developing stories over flat suppression).

Runs against a local Ollama server (no API key, nothing leaves the laptop —
decided in conversation after the PRD's "no server, no hosting" non-goal
turned out to mean this literally). Also decided: one combined
rank+summarize call, not two. World and AI summaries in English, Chile in
Spanish.
"""

from __future__ import annotations

import json
import os

import requests

import backlog as backlog_module

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
REQUEST_TIMEOUT = 180  # local inference on a laptop CPU/GPU can be slow

ITEMS_PER_CATEGORY = 3

_LANGUAGE_NAME = {"en": "English", "es": "Spanish"}


def _prepare_candidates(candidates: list[dict], source_counts: dict[str, int] | None) -> list[dict]:
    """Attach backlog match info to each candidate, and source-count (from
    clustering) when given — World/AI only, Chile passes None."""
    backlog_entries = backlog_module.load()
    prepared = []
    for c in candidates:
        match = backlog_module.find_match(c, backlog_entries)
        entry = {
            "title": c["title"],
            "url": c["url"],
            "source": c["source"],
            "published": c["published"],
        }
        if source_counts is not None:
            entry["source_count"] = source_counts.get(c["title"], 1)
        if match:
            entry["previously_sent"] = {"date": match["date"], "summary": match["summary"]}
        prepared.append(entry)
    return prepared


def _build_prompt(category: str, candidates: list[dict], preferences: str, language: str) -> str:
    lang_name = _LANGUAGE_NAME[language]
    prefs_block = preferences if preferences else "(none set)"
    return f"""You are selecting and summarising the "{category}" section of a daily \
Kindle news digest for one reader. Pick the {ITEMS_PER_CATEGORY} most important items \
from the candidates below — importance, not recency, and not simply how \
many sources covered something (that signal, where present, is already \
reflected in source_count).

Reader's standing preferences (steer selection toward these, they are not \
optional flavour text):
{prefs_block}

Some candidates were already sent in a previous edition within the last 7 \
days — these carry a "previously_sent" field with the date and summary that \
went out. For those: if there is genuinely nothing new, do not select them \
again. If the story has developed, you may select it again but the summary \
must be framed as an update — state what's changed since the prior summary, \
don't repeat it.

Write every summary in {lang_name}, 1-2 sentences, dense with the actual \
news (not "here is an article about...").

Candidates:
{json.dumps(candidates, ensure_ascii=False, indent=2)}

Respond with ONLY a JSON object, no other text: {{"items": [...]}} where \
each element of "items" is {{"title": <original candidate title>, "url": \
<original candidate url>, "summary": <your summary>, "is_update": <true if \
this reframes a previously_sent item, else false>}}. At most \
{ITEMS_PER_CATEGORY} elements, fewer only if fewer candidates genuinely \
deserve a place."""


def _call_model(prompt: str) -> list[dict]:
    response = requests.post(
        f"{OLLAMA_HOST}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "format": "json",
            "stream": False,
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    raw = response.json()["response"]
    parsed = json.loads(raw)
    return parsed["items"]


def select_top_three(
    candidates: list[dict],
    preferences: str,
    category: str,
    language: str = "en",
    source_counts: dict[str, int] | None = None,
) -> list[dict]:
    """Return up to ITEMS_PER_CATEGORY items for one category, each with a
    1-2 sentence summary in the given language ("en" or "es")."""
    if not candidates:
        return []
    prepared = _prepare_candidates(candidates, source_counts)
    prompt = _build_prompt(category, prepared, preferences, language)
    selected = _call_model(prompt)
    return selected[:ITEMS_PER_CATEGORY]
