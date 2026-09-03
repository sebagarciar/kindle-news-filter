"""Article fetch and embedding. PRD 5.4.

trafilatura extracts clean text. Fallback chain when extraction fails or the
article is paywalled:
  1. RSS description/excerpt, if substantial enough to stand alone
  2. Summary + external link, marked visibly "full text unavailable"

Long articles get truncated with a visible note rather than risking the
Send-to-Kindle email size limit — see epub_builder.py for the size check.
"""


def fetch_article_text(url: str, fallback_summary: str) -> dict:
    """Return {"text": str, "truncated": bool, "full_text_available": bool}."""
    raise NotImplementedError
