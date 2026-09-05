"""Shared text helpers for summary quality.

Redundancy detection lives here rather than in epub_builder.py because two
stages need the same answer to the same question: rank.py, to decide
whether the model's summary is worth keeping or should be replaced by the
RSS excerpt, and epub_builder.py, as the last line of defence before a
reader has to read the same sentence twice in a row.

Word overlap, not similarity scoring — this stays dependency-free and
works for both the English and Spanish sections.
"""

from __future__ import annotations

import re

REDUNDANCY_THRESHOLD = 0.5

_STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or",
    "is", "are", "was", "were", "be", "as", "by", "with", "from", "after",
    "over", "into", "amid", "its", "his", "her", "their", "says", "said",
    "has", "have", "had", "it", "this", "that", "than", "but", "not",
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "en",
    "y", "o", "que", "con", "para", "por", "su", "sus", "del", "al",
    "ha", "han", "es", "son", "se", "lo", "más", "como", "entre", "sin",
}
_WORD_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9]+")
_SUFFIXES = ("mente", "iendo", "ando", "ing", "es", "ed", "s")

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

# RSS descriptions are HTML fragments with real block structure, and that
# structure is the only thing separating an article's first sentence from
# the newsletter box sitting above it. Flattening the whole fragment to one
# line loses that, which is how "Sign up for US Breaking News emails" once
# ended up mid-summary.
_BLOCK_END_RE = re.compile(r"</(?:p|div|li|ul|ol|h[1-6]|blockquote|tr)>|<br\s*/?>", re.I)

# Blocks that are site furniture, not news, in either digest language.
_CHROME_RE = re.compile(
    r"^(?:sign up|subscribe|continue reading|read more|read next|follow us|"
    r"share this|share on|download|get the|newsletter|advertisement|"
    r"photograph|suscr[ií]bete|sigue leyendo|lee m[aá]s|lee tambi[eé]n|"
    r"te puede interesar|m[aá]s informaci[oó]n|comparte(?:\s+esta)?|"
    r"s[ií]guenos|comentarios?|comments?|leave a (?:reply|comment)|"
    r"join the conversation|view comments|deja tu comentario|click here|"
    r"haz clic aqu[ií]|related(?:\s+(?:articles?|stories|reading))?|"
    r"recommended for you|you might also like|"
    r"\d+\s*(?:comments?|comentarios?))\b",
    re.I,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def content_tokens(text: str) -> list[str]:
    words = _WORD_RE.findall((text or "").lower())
    return [_stem(w) for w in words if w not in _STOPWORDS and len(w) > 2]


def is_redundant_summary(title: str, summary: str) -> bool:
    """True if the summary is mostly just the title's words rearranged."""
    summary_tokens = content_tokens(summary)
    title_tokens = set(content_tokens(title))
    if len(summary_tokens) < 4 or not title_tokens:
        return False
    overlap = sum(1 for t in summary_tokens if t in title_tokens)
    return (overlap / len(summary_tokens)) >= REDUNDANCY_THRESHOLD


def text_blocks(text: str) -> list[str]:
    """Split an HTML fragment into plain-text blocks, dropping site
    furniture (newsletter sign-ups, "Continue reading...") outright."""
    marked = _BLOCK_END_RE.sub("\n", text or "")
    blocks = []
    for raw in marked.split("\n"):
        block = _WHITESPACE_RE.sub(" ", _TAG_RE.sub(" ", raw)).strip()
        if block and not _CHROME_RE.match(block):
            blocks.append(block)
    return blocks


def clean_text(text: str) -> str:
    """Chrome-free plain text — what the model should see."""
    return " ".join(text_blocks(text))


def strip_boilerplate(text: str) -> str:
    """Drop paragraphs that are site furniture rather than article text —
    comment counters, "click here to subscribe", share prompts, related-
    reading blocks. Unlike text_blocks/clean_text, this works on trafilatura's
    plain-text output (blank-line-separated paragraphs, no HTML), which is
    what fetch.py embeds in the EPUB. Same _CHROME_RE, since it's the same
    junk in either shape."""
    blocks = [b.strip() for b in (text or "").split("\n\n")]
    kept = [b for b in blocks if b and not _CHROME_RE.match(b)]
    return "\n\n".join(kept)


def lead_sentences(text: str, limit: int) -> str:
    """The best 1-2 whole sentences an excerpt can offer, for use as a
    summary when the model's own summary is unusable.

    Prefers the first block that is actually a sentence: a standfirst
    often has no full stop and reads as a fragment, while the paragraph
    below it is the real opening line of the article.
    """
    blocks = text_blocks(text)
    if not blocks:
        return ""
    base = next((b for b in blocks if b.rstrip().endswith((".", "!", "?"))), None)
    if base is None:
        base = max(blocks, key=len)

    out = ""
    for sentence in _SENTENCE_SPLIT_RE.split(base)[:2]:
        candidate = f"{out} {sentence}".strip()
        if out and len(candidate) > limit:
            break
        out = candidate
    return out[:limit].strip() if len(out) > limit else out
