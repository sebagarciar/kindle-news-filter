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

import re

import trafilatura

import text_utils

MIN_SUMMARY_CHARS = 200  # below this, a bare RSS excerpt can't "stand alone"
TRUNCATE_CHARS = 8000


SUBHEAD_MARK = "## "


def _mark_subheadings(text: str, downloaded: str) -> str:
    """Prefix the article's own subheadings with "## ".

    trafilatura's plain text turns a subheading into a paragraph like any
    other, so on the Kindle it looked like body text. Its markdown output
    keeps the heading marks, so read the heading texts from there and tag
    the matching lines. epub_builder.py renders the tagged lines as headings.
    """
    markdown = trafilatura.extract(downloaded, output_format="markdown") or ""
    heads = {m.group(1).strip() for m in re.finditer(r"^#{1,6}\s+(.+)$", markdown, re.M)}
    if not heads:
        return text
    blocks = [SUBHEAD_MARK + b if b in heads else b for b in text.split("\n\n")]
    return "\n\n".join(blocks)


def fetch_article_text(url: str, fallback_summary: str) -> dict:
    """Return {"text": str, "truncated": bool, "full_text_available": bool}."""
    text = None
    if url:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded)
            if text:
                # trafilatura strips most nav/ads but regularly leaves a
                # trailing "Comments" or "Click here to subscribe" paragraph
                # behind, since that's article-adjacent text, not markup it
                # can tell apart structurally. Its output has one paragraph
                # per line, and strip_boilerplate also turns that into
                # blank-line-separated paragraphs: left as single lines, a
                # whole article reached the Kindle as one <p>.
                text = text_utils.strip_boilerplate(text)
                text = _mark_subheadings(text, downloaded)

    if text and text.strip():
        truncated = len(text) > TRUNCATE_CHARS
        if truncated:
            text = text[:TRUNCATE_CHARS].rstrip() + "\n\n[Article cut here: too long for this edition.]"
        return {"text": text, "truncated": truncated, "full_text_available": True}

    clean_summary = fallback_summary.strip()
    if len(clean_summary) >= MIN_SUMMARY_CHARS:
        return {"text": clean_summary, "truncated": False, "full_text_available": False}

    note = f"{clean_summary}\n\n[Full text unavailable. Read the original at the link below.]" if url else clean_summary
    return {"text": note, "truncated": False, "full_text_available": False}
