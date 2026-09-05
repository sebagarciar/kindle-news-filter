"""YouTube read-later items. PRD 5.6, extended per feedback after live use.

A YouTube link has no article text for fetch.py's trafilatura path to pull —
there's a video, not a page of prose. What Kindle can actually use is the
video's transcript, but a raw transcript is auto-captioned word soup with no
punctuation or paragraphs, unreadable at any length. So this fetches the
transcript locally, then asks the same local Ollama model rank.py already
uses to turn it into readable prose. Nothing here leaves the laptop except
the two calls any read-later link already makes to the web: one to YouTube's
public oEmbed endpoint for the title, one to its public transcript endpoint
for captions.

The output is reading notes, not a blurb. The first version asked for 3-5
sentences and that came back too thin to learn anything from: a video is
queued precisely because it's worth an hour of someone's attention, so the
notes have to carry the argument, the specifics behind it, and whatever in
it is actually usable. Two things follow from that:

  - Length is bounded by the transcript, not by the model's context window.
    A talk runs well past what an 8B model can hold at once, so long
    transcripts are read in chunks, each chunk noted, and the notes merged
    into one piece. The alternative — summarizing the first 12k characters
    and calling it the video — silently drops the second half of every
    lecture, which is usually where the conclusions are.
  - The prompt asks for the teachable substance explicitly (methods, rules
    of thumb, mistakes, recommendations) but only where the video really
    offers it, since inviting a model to find lessons in a news clip is
    inviting it to invent them.

Falls back gracefully at every stage (no transcript available, transcript
fetch blocked, model call fails, some chunks fail) rather than raising — a
queued video must never take down the whole edition, same rule fetch.py
follows for articles.
"""

from __future__ import annotations

import re

import requests
from youtube_transcript_api import YouTubeTranscriptApi

import llm
import text_utils

_URL_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)

# Roughly an hour of speech. Past this the returns fall off fast: the tail of
# a long video is usually Q&A, and four model calls already cost a couple of
# minutes on a laptop.
CHUNK_CHARS = 14000
MAX_CHUNKS = 4

# Ollama defaults to a context far smaller than a chunk, and truncates
# silently — see llm.py. 8192 holds a chunk plus its notes with room spare.
_LLM_OPTIONS = {"num_ctx": 8192, "temperature": 0.3}
_LLM_TIMEOUT = 300

# Preferred caption languages, in order. Anything else still gets used if
# it's the only track there; the notes are then written in English.
_TRANSCRIPT_LANGUAGES = ["en", "es"]

_OEMBED_TIMEOUT = 10

# Length of the one-paragraph version shown on the Read Later TL;DR page,
# before the reader taps through to the full notes.
_TLDR_CHARS = 300

_NOTES_PROMPT = """You are writing reading notes for someone who will read them on a Kindle instead of watching the video{title_clause}. They queued it to learn from it, so detail matters more than brevity.

Write 400 to 550 words in {language}, as plain prose paragraphs separated by blank lines, covering in this order:
1. one opening sentence naming the subject and the central claim.
2. the substance: the specific claims, numbers, names, examples, steps and definitions the argument rests on. Where the video gives a list — questions to ask, steps to follow, rules, examples — write the items out instead of saying that a list was given.
3. what a reader could actually use to get better at their work or their thinking: methods, frameworks, rules of thumb, mistakes to avoid, tools or books recommended. Include this only if the video genuinely offers it. If it doesn't, leave it out rather than inventing it.

Rules: write the content itself, not a description of the video. "Most founders pick the idea before the problem, which is why X" — never "the video discusses" or "the speaker recommends". Use only what is in the transcript, never fill gaps from your own knowledge. No markdown, no bullet characters, no headings, no preamble, no sign-off — start with the first sentence of the notes.

Transcript:
{transcript}"""


_CHUNK_PROMPT = """The following is part {index} of {total} of an auto-generated transcript of one YouTube video{title_clause}.

Take notes on this part in 200 to 300 words of plain prose, in {language}. Keep every specific: claims, numbers, names, examples, steps, definitions, advice. Where this part gives a list — questions, steps, rules, recipes, examples — write the items out rather than mentioning that a list exists; a later pass can only keep what these notes keep.

Write the content itself, not a description of the video: "X fails because Y", never "the speaker explains X". Use only what is in this part, and do not summarize what you think came before or after it. No markdown, no bullet characters, no preamble.

Transcript part {index}:
{transcript}"""


_MERGE_PROMPT = """Below are sequential notes taken from consecutive parts of one YouTube video's transcript{title_clause}. They are notes, not the video: your job is to turn them into the finished reading notes.

Write 500 to 750 words in {language}, as plain prose paragraphs separated by blank lines, covering in this order:
1. one opening sentence naming the subject and the central claim.
2. the substance: the specific claims, numbers, names, examples, steps and definitions the argument rests on. Carry across every specific the notes contain — where they list questions, steps, rules or examples, write the items out rather than referring to the list.
3. what a reader could actually use to get better at their work or their thinking: methods, frameworks, rules of thumb, mistakes to avoid, tools or books recommended. Include this only if the notes genuinely contain it.

Rules: write the content itself, not a description of the video. "Ideas with existing competitors are the safer bet, because X" — never "the video discusses" or "the speaker recommends". Use only what is in the notes, never fill gaps from your own knowledge. Do not mention parts, notes, or the transcript itself — write as if you had watched the whole video. No markdown, no bullet characters, no headings, no preamble, no sign-off.

Notes:
{notes}"""


_PREAMBLE_RE = re.compile(
    r"^(?:here (?:is|are)|sure|of course|below (?:is|are)|these are|the following)\b[^\n]{0,120}:\s*",
    re.I,
)
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.M)
_HEADING_RE = re.compile(r"^\s*#{1,6}\s*", re.M)
_BLANKS_RE = re.compile(r"\n{3,}")


def extract_video_id(url: str) -> str | None:
    match = _URL_RE.search(url or "")
    return match.group(1) if match else None


def is_youtube_url(url: str) -> bool:
    return extract_video_id(url) is not None


def fetch_title(url: str) -> str | None:
    try:
        response = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
            timeout=_OEMBED_TIMEOUT,
        )
        response.raise_for_status()
        title = response.json().get("title", "").strip()
        return title or None
    except Exception:
        return None


def fetch_transcript(video_id: str) -> tuple[str | None, str | None]:
    """Return (transcript text, language code), or (None, None).

    Prefers an English or Spanish track and falls back to whatever track the
    video has, rather than failing outright the way an English-only fetch
    does on a Spanish video. Disabled captions, an age-gated or unavailable
    video, and an IP-level block from YouTube's endpoint all land here and
    degrade the same way, to the fallback in fetch_video_summary below.
    """
    try:
        available = YouTubeTranscriptApi().list(video_id)
        try:
            transcript = available.find_transcript(_TRANSCRIPT_LANGUAGES)
        except Exception:
            transcript = next(iter(available))
        fetched = transcript.fetch()
    except Exception:
        return None, None

    text = " ".join(snippet.text.strip() for snippet in fetched if snippet.text.strip())
    return (text, transcript.language_code) if text else (None, None)


def _output_language(language_code: str | None) -> str:
    """Spanish videos get Spanish notes; everything else, including French or
    German talks, gets English ones — this digest's reader reads both."""
    return "Spanish" if (language_code or "").lower().startswith("es") else "English"


def _chunk(text: str) -> list[str]:
    """Split on whitespace near CHUNK_CHARS so no sentence is cut mid-word."""
    chunks = []
    remaining = text.strip()
    while remaining and len(chunks) < MAX_CHUNKS:
        if len(remaining) <= CHUNK_CHARS:
            chunks.append(remaining)
            break
        split_at = remaining.rfind(" ", 0, CHUNK_CHARS)
        if split_at <= 0:
            split_at = CHUNK_CHARS
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return chunks


def _tidy(text: str) -> str:
    """Strip the model's habitual preamble and any markdown it added despite
    being told not to — the EPUB renders plain text, so a stray '**' or '- '
    reaches the Kindle screen as literal characters."""
    out = _PREAMBLE_RE.sub("", (text or "").strip())
    out = _HEADING_RE.sub("", out)
    out = _BULLET_RE.sub("", out)
    out = out.replace("**", "").replace("__", "")
    return _BLANKS_RE.sub("\n\n", out).strip()


def _generate(prompt: str, max_tokens: int) -> str | None:
    try:
        result = llm.generate(
            prompt,
            options={**_LLM_OPTIONS, "num_predict": max_tokens},
            timeout=_LLM_TIMEOUT,
        )
    except Exception:
        return None
    tidied = _tidy(result)
    return tidied or None


def _title_clause(title: str | None) -> str:
    return f' titled "{title}"' if title else ""


def write_notes(transcript: str, title: str | None, language_code: str | None) -> str | None:
    """Reading notes for a whole transcript, in one pass when it fits and via
    per-chunk notes plus a merge when it doesn't. A chunk whose model call
    fails is skipped rather than aborting the video, and if the merge itself
    fails the per-chunk notes go out as they are: less polished than the
    merged version, but still the whole video rather than none of it."""
    chunks = _chunk(transcript)
    if not chunks:
        return None

    language = _output_language(language_code)
    title_clause = _title_clause(title)

    if len(chunks) == 1:
        return _generate(
            _NOTES_PROMPT.format(title_clause=title_clause, language=language, transcript=chunks[0]),
            max_tokens=1000,
        )

    notes = []
    for index, chunk in enumerate(chunks, start=1):
        part = _generate(
            _CHUNK_PROMPT.format(
                index=index,
                total=len(chunks),
                title_clause=title_clause,
                language=language,
                transcript=chunk,
            ),
            max_tokens=600,
        )
        if part:
            notes.append(part)

    if not notes:
        return None
    merged = _generate(
        _MERGE_PROMPT.format(title_clause=title_clause, language=language, notes="\n\n".join(notes)),
        max_tokens=1400,
    )
    return merged or "\n\n".join(notes)


def fetch_video_summary(url: str, fallback_text: str) -> dict:
    """Return {"title", "summary", "text", "full_text_available"}.

    title is the fetched video title, or None if oEmbed failed (caller should
    keep its own fallback title in that case). text is the full reading
    notes; summary is the opening sentences of those notes, for the TL;DR
    page that sits in front of them. When the transcript or the model call
    can't deliver, both fall back to something that still tells the reader
    what happened and hands them the link.
    """
    video_id = extract_video_id(url)
    title = fetch_title(url) if video_id else None

    transcript, language_code = fetch_transcript(video_id) if video_id else (None, None)
    if transcript:
        notes = write_notes(transcript, title, language_code)
        if notes:
            return {
                "title": title,
                "summary": text_utils.lead_sentences(notes, _TLDR_CHARS) or notes[:_TLDR_CHARS],
                "text": notes,
                "full_text_available": True,
            }

    clean_fallback = (fallback_text or "").strip()
    reason = "no transcript available" if not transcript else "summarization failed"
    note = f"{clean_fallback}\n\n[Video — {reason}. Watch it here: {url}]" if url else clean_fallback
    return {"title": title, "summary": clean_fallback[:_TLDR_CHARS], "text": note, "full_text_available": False}
