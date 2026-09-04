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

Each candidate is handed to the model with its RSS excerpt attached.
Without it the model sees nothing but a headline, so the best it can do
is reword one — which is exactly what it did to the Chile section, whose
local stories it has no background knowledge of. See
_apply_summary_fallback for what happens when it rewords one anyway.

Runs against a local Ollama server (no API key, nothing leaves the laptop —
decided in conversation after the PRD's "no server, no hosting" non-goal
turned out to mean this literally). Also decided: one combined
rank+summarize call, not two. World and AI summaries in English, Chile in
Spanish.
"""

from __future__ import annotations

import json

import backlog as backlog_module
import llm
import text_utils

ITEMS_PER_CATEGORY = 3

# How much of the RSS excerpt the model gets per candidate. Enough to
# carry the facts the headline leaves out, short enough that 15
# candidates still fit comfortably in one local-model prompt.
EXCERPT_CHARS = 500

# Ceiling for an excerpt used verbatim as the fallback summary.
FALLBACK_SUMMARY_CHARS = 300

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
        excerpt = text_utils.clean_text(c.get("summary", ""))[:EXCERPT_CHARS]
        if excerpt:
            entry["excerpt"] = excerpt
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

Most candidates carry an "excerpt" — the opening of the article itself. \
That excerpt, not your own knowledge, is where the summary comes from: it \
is the only place the facts a headline leaves out are actually written \
down, and for local Chilean stories it is the only thing you know about \
the story at all. Where a candidate has no excerpt, summarise only what \
you can genuinely support, and never invent a number, a name or a cause.

Write every summary in {lang_name}, 1-2 sentences, dense with the actual \
news (not "here is an article about..."). The reader already sees the \
title before the summary, so the summary must add something the title \
doesn't already say — a number, a name, a cause, or a consequence, taken \
from the excerpt. Don't just restate the title in different words: a \
summary that only rearranges the headline's own words is worse than no \
summary and will be thrown away.

Candidates:
{json.dumps(candidates, ensure_ascii=False, indent=2)}

Respond with ONLY a JSON object, no other text: {{"items": [...]}} where \
each element of "items" is {{"title": <original candidate title>, "url": \
<original candidate url>, "summary": <your summary>, "is_update": <true if \
this reframes a previously_sent item, else false>}}. At most \
{ITEMS_PER_CATEGORY} elements, fewer only if fewer candidates genuinely \
deserve a place."""


def _call_model(prompt: str) -> list[dict]:
    raw = llm.generate(prompt, json_mode=True)
    parsed = json.loads(raw)
    return parsed["items"]


def _apply_summary_fallback(selected: list[dict], candidates: list[dict]) -> list[dict]:
    """Replace a summary that just rearranges the title with the article's
    own excerpt.

    A local 8B model told not to restate the headline still does it,
    especially in Spanish on local Chilean stories it has no background
    knowledge of. epub_builder drops a summary like that rather than make
    the reader read the same sentence twice, which used to leave a bare
    title on the page. The excerpt is a worse summary than a good model
    summary and a much better one than nothing.
    """
    excerpts = {}
    for c in candidates:
        excerpt = text_utils.lead_sentences(c.get("summary", ""), FALLBACK_SUMMARY_CHARS)
        if excerpt:
            excerpts[c["url"]] = excerpt
            excerpts[c["title"]] = excerpt

    for item in selected:
        summary = (item.get("summary") or "").strip()
        if summary and not text_utils.is_redundant_summary(item.get("title", ""), summary):
            continue
        excerpt = excerpts.get(item.get("url", "")) or excerpts.get(item.get("title", ""), "")
        if excerpt and not text_utils.is_redundant_summary(item.get("title", ""), excerpt):
            item["summary"] = excerpt
        else:
            item["summary"] = summary
    return selected


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
    selected = _call_model(prompt)[:ITEMS_PER_CATEGORY]
    return _apply_summary_fallback(selected, candidates)
