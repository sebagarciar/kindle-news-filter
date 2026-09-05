"""EPUB assembly. PRD 5.8, revised twice after live testing.

Tap-through structure:

  Main landing (World / AI / Chile / Read Later, each a heading with its
    headlines underneath — titles only, no summaries, so it fits one small
    screen)
    -> tap a title -> TL;DR page (title + summary + "Full article ->",
       summary omitted when it's redundant with the title — see
       text_utils.is_redundant_summary, and rank.py can now also just leave
       it blank itself when the title already says everything)
      -> tap that -> full article page
    -> TL;DR page and full article page each have "<- Back", which jumps to
       that item's own section heading on the landing page (an in-page
       anchor), not to the top of the landing — so reading a Chile item and
       tapping Back lands you back among the Chile headlines, not scrolled
       past them to World.

Read Later used to get its own second landing page. Folded into the main
one as a fourth section (same shape as World/AI/Chile) after feedback that
a separate page for it was more navigation, not less.

Every headline is also registered as its own chapter in the EPUB's nav/NCX
(nested under its section), pointing at that item's TL;DR page. That's what
turns on a Kindle's "time left in chapter" estimate per headline — the
chapter runs from the TL;DR page through the full article, ending where the
next headline's TL;DR page begins, so the estimate covers exactly the
"how long is this one" question, not the whole edition.

Still owns the total-size check against Amazon's send-to-Kindle email limit
(PRD 5.4, 5.10) — if the assembled book is still too big after fetch.py's
per-article truncation, that should be caught here rather than letting
delivery fail silently.
"""

from __future__ import annotations

import html
import os
import tempfile

from ebooklib import epub

import text_utils

# Send-to-Kindle's documented email/attachment limit is 50MB; staying well
# under it leaves room for MIME/base64 overhead in deliver.py.
MAX_EPUB_BYTES = 40 * 1024 * 1024

SECTIONS = ["World", "AI", "Chile", "Read Later"]
LANG_BY_SECTION = {"World": "en", "AI": "en", "Chile": "es", "Read Later": "en"}

LANDING_FILE = "index.xhtml"

BACK_ARROW = "←"
FORWARD_ARROW = "→"


def _esc(text: str) -> str:
    return html.escape(text or "")


def _slug(section_name: str, i: int) -> str:
    return f"{section_name.lower().replace(' ', '_')}_{i}"


def _section_anchor(section_name: str) -> str:
    return section_name.lower().replace(" ", "_")


def _tldr_html(item: dict, landing_href: str, full_href: str) -> str:
    source_line = f"<p><em>{_esc(item.get('source', ''))}</em></p>" if item.get("source") else ""
    summary = item.get("summary", "")
    show_summary = bool(summary) and not text_utils.is_redundant_summary(item["title"], summary)
    summary_line = f"<p>{_esc(summary)}</p>" if show_summary else ""
    return (
        f"<h2>{_esc(item['title'])}</h2>"
        f"{source_line}"
        f"{summary_line}"
        f'<p><a href="{full_href}">Full article {FORWARD_ARROW}</a></p>'
        f"<hr/>"
        f'<p><a href="{landing_href}">{BACK_ARROW} Back</a></p>'
    )


def _paragraphs_html(text: str) -> str:
    """Blank-line-separated blocks become real paragraphs, single newlines
    stay line breaks inside one. Extracted article text and the video notes
    both arrive with that structure, and a Kindle renders one 500-word <p>
    as an unbroken wall."""
    blocks = [block.strip() for block in (text or "").split("\n\n")]
    return "".join(f"<p>{_esc(block).replace(chr(10), '<br/>')}</p>" for block in blocks if block)


def _full_html(item: dict, landing_href: str) -> str:
    body = _paragraphs_html(item.get("text", ""))
    link_line = f'<p><a href="{_esc(item["url"])}">{_esc(item["url"])}</a></p>' if item.get("url") else ""
    return (
        f"<h2>{_esc(item['title'])}</h2>"
        f"{body}"
        f"{link_line}"
        f"<hr/>"
        f'<p><a href="{landing_href}">{BACK_ARROW} Back</a></p>'
    )


def _landing_html(heading: str, status_line: str | None, groups: list[tuple[str, list[tuple[str, str]]]]) -> str:
    parts = [f"<h1>{_esc(heading)}</h1>"]
    if status_line:
        parts.append(f'<p style="color:#900"><strong>{_esc(status_line)}</strong></p>')
    for section_name, entries in groups:
        if not entries:
            continue
        parts.append(f'<h3 id="{_section_anchor(section_name)}">{_esc(section_name)}</h3>')
        parts.append("<ul>")
        for title, href in entries:
            parts.append(f'<li><a href="{href}">{_esc(title)}</a></li>')
        parts.append("</ul>")
    return "".join(parts)


def _add_item_pages(book: epub.EpubBook, section_name: str, items: list[dict], lang: str) -> tuple[list[tuple[str, str]], list]:
    """Create a TL;DR + full-article chapter pair per item. Returns
    (landing entries as (title, tldr_href), chapters in reading order)."""
    landing_href = f"{LANDING_FILE}#{_section_anchor(section_name)}"
    entries = []
    chapters = []
    for i, item in enumerate(items):
        tldr_fn = f"{_slug(section_name, i)}_tldr.xhtml"
        full_fn = f"{_slug(section_name, i)}_full.xhtml"
        display_title = item["title"] + (" (update)" if item.get("is_update") else "")

        tldr_chapter = epub.EpubHtml(title=display_title, file_name=tldr_fn, lang=lang)
        tldr_chapter.content = _tldr_html({**item, "title": display_title}, landing_href, full_fn)
        full_chapter = epub.EpubHtml(title=display_title, file_name=full_fn, lang=lang)
        full_chapter.content = _full_html({**item, "title": display_title}, landing_href)

        book.add_item(tldr_chapter)
        book.add_item(full_chapter)
        chapters.extend([tldr_chapter, full_chapter])
        entries.append((display_title, tldr_fn))
    return entries, chapters


def build_epub(edition_date: str, sections: dict[str, list[dict]], status_line: str | None) -> bytes:
    """Assemble the day's edition into EPUB bytes.

    sections maps section name -> list of items, each with at least
    'title', 'summary', 'text'; 'source', 'url', 'is_update' are optional.
    Expected keys: "World", "AI", "Chile", "Read Later", all on one landing
    page in that order (PRD 5.8). status_line, if set, renders at the top
    per PRD 5.10 failure handling.
    """
    book = epub.EpubBook()
    book.set_identifier(f"kindle-news-{edition_date}")
    book.set_title(f"News Digest — {edition_date}")
    book.set_language("en")

    groups = []
    all_chapters = []
    toc = [epub.Link(LANDING_FILE, "News Digest", "landing")]
    for section_name in SECTIONS:
        entries, chapters = _add_item_pages(book, section_name, sections.get(section_name, []), LANG_BY_SECTION[section_name])
        groups.append((section_name, entries))
        all_chapters.extend(chapters)
        if entries:
            anchor = _section_anchor(section_name)
            section_links = [epub.Link(href, title, f"{anchor}_{i}") for i, (title, href) in enumerate(entries)]
            toc.append((epub.Section(section_name), section_links))

    main_landing = epub.EpubHtml(title="News Digest", file_name=LANDING_FILE, lang="en")
    main_landing.content = _landing_html(f"News Digest — {edition_date}", status_line, groups)
    book.add_item(main_landing)

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = [main_landing, *all_chapters, "nav"]

    fd, tmp_path = tempfile.mkstemp(suffix=".epub")
    os.close(fd)
    try:
        epub.write_epub(tmp_path, book)
        with open(tmp_path, "rb") as f:
            data = f.read()
    finally:
        os.remove(tmp_path)

    if len(data) > MAX_EPUB_BYTES:
        raise ValueError(
            f"Edition is {len(data) / 1024 / 1024:.1f}MB, over the {MAX_EPUB_BYTES / 1024 / 1024:.0f}MB "
            "budget even after per-article truncation — reduce TRUNCATE_CHARS in fetch.py."
        )
    return data
