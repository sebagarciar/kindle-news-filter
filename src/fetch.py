"""Article fetch and embedding. PRD 5.4.

trafilatura extracts clean text. Fallback chain when extraction fails or the
article is paywalled:
  1. RSS description/excerpt, if substantial enough to stand alone
  2. Summary + external link, marked visibly "full text unavailable"

Long articles get truncated with a visible note — see TRUNCATE_CHARS —
rather than risking the Send-to-Kindle email size limit (checked in bulk
against the whole edition in epub_builder.py).
"""

from __future__ import annotations

import trafilatura

MIN_SUMMARY_CHARS = 200  # below this, a bare RSS excerpt can't "stand alone"
TRUNCATE_CHARS = 8000


def fetch_article_text(url: str, fallback_summary: str) -> dict:
    """Return {"text": str, "truncated": bool, "full_text_available": bool}."""
    text = None
    if url:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded)

    if text and text.strip():
        truncated = len(text) > TRUNCATE_CHARS
        if truncated:
            text = text[:TRUNCATE_CHARS].rstrip() + "\n\n[Truncated — full article too long for this edition.]"
        return {"text": text, "truncated": truncated, "full_text_available": True}

    clean_summary = fallback_summary.strip()
    if len(clean_summary) >= MIN_SUMMARY_CHARS:
        return {"text": clean_summary, "truncated": False, "full_text_available": False}

    note = f"{clean_summary}\n\n[Full text unavailable — read the original: {url}]" if url else clean_summary
    return {"text": note, "truncated": False, "full_text_available": False}
