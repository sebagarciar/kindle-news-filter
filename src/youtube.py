"""YouTube read-later items. PRD 5.6, extended per feedback after live use.

A YouTube link has no article text for fetch.py's trafilatura path to pull —
there's a video, not a page of prose. What Kindle can actually use is the
video's transcript, but a raw transcript is auto-captioned word soup with no
punctuation or paragraphs, unreadable at any length. So this fetches the
transcript locally, then asks the same local Ollama model rank.py already
uses to turn it into a short prose summary. Nothing here leaves the laptop
except the two calls any read-later link already makes to the web: one to
YouTube's public oEmbed endpoint for the title, one to its public transcript
endpoint for captions.

Falls back gracefully at every stage (no transcript available, transcript
fetch blocked, model call fails) rather than raising — a queued video must
never take down the whole edition, same rule fetch.py follows for articles.
"""

from __future__ import annotations

import re

import requests
from youtube_transcript_api import YouTubeTranscriptApi

import llm

_URL_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)

# Caps how much transcript text goes into the summarization prompt — a
# 90-minute video's transcript can run past 50k characters, more than the
# local model's context window can hold. The summary comes from whatever
# fits, not the whole thing; there's no truncation note in the output
# because the output is already a summary, not a claim of completeness.
TRANSCRIPT_CHARS_FOR_SUMMARY = 12000

_OEMBED_TIMEOUT = 10


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


def fetch_transcript_text(video_id: str) -> str | None:
    # Disabled captions, an age-gated/unavailable video, or an IP-level
    # block from YouTube's endpoint all land here — every case degrades the
    # same way, to the fallback in fetch_video_summary below.
    try:
        fetched = YouTubeTranscriptApi().fetch(video_id)
    except Exception:
        return None
    text = " ".join(snippet.text.strip() for snippet in fetched if snippet.text.strip())
    return text or None


def _summarize(transcript: str, title: str | None) -> str | None:
    prompt = f"""The following is an auto-generated transcript of a YouTube video\
{f' titled "{title}"' if title else ''}. Write a summary in 3-5 sentences \
covering the actual content and key points — not "this video is about...". \
If the transcript cuts off mid-thought, summarize what's there rather than \
noting that it's incomplete.

Transcript:
{transcript[:TRANSCRIPT_CHARS_FOR_SUMMARY]}

Respond with ONLY the summary, no preamble."""
    try:
        return llm.generate(prompt).strip()
    except Exception:
        return None


def fetch_video_summary(url: str, fallback_text: str) -> dict:
    """Return {"title": str | None, "text": str, "full_text_available": bool}.

    title is the fetched video title, or None if oEmbed failed (caller should
    keep its own fallback title in that case). text is a model-written
    summary of the transcript when both the transcript and the model call
    succeed; otherwise a fallback that still tells the reader what happened
    and gives them the link.
    """
    video_id = extract_video_id(url)
    title = fetch_title(url) if video_id else None

    transcript = fetch_transcript_text(video_id) if video_id else None
    if transcript:
        summary = _summarize(transcript, title)
        if summary:
            return {"title": title, "text": summary, "full_text_available": True}

    clean_fallback = (fallback_text or "").strip()
    reason = "no transcript available" if not transcript else "summarization failed"
    note = f"{clean_fallback}\n\n[Video — {reason}. Watch it here: {url}]" if url else clean_fallback
    return {"title": title, "text": note, "full_text_available": False}
