"""EPUB assembly. PRD 5.8, revised per feedback after the first test edition.

Original design (flat TOC, full text inline under each headline) didn't
work on a Kindle screen. Replaced with a tap-through structure:

  Main landing (9 titles, grouped World/AI/Chile, no summaries — just
  titles, so it fits one small screen)
    -> tap a title -> TL;DR page (title + summary + "Full article ->",
       summary omitted when it's just the title reworded — see
       text_utils.is_redundant_summary)
      -> tap that -> full article page
    -> TL;DR page and full article page each have "<- Back" to the landing
       they came from

Read Later items get their own second landing page rather than being mixed
into the main 9, for the same small-screen reason — their "Back" links
return to the Read Later landing, not the main one, so the two flows never
cross.

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

NEWS_SECTIONS = ["World", "AI", "Chile"]
LANG_BY_SECTION = {"World": "en", "AI": "en", "Chile": "es"}

LANDING_FILE = "index.xhtml"
READ_LATER_LANDING_FILE = "read_later.xhtml"

BACK_ARROW = "←"
FORWARD_ARROW = "→"


def _esc(text: str) -> str:
    return html.escape(text or "")


def _slug(section_name: str, i: int) -> str:
    return f"{section_name.lower().replace(' ', '_')}_{i}"


def _tldr_html(item: dict, landing_href: str, full_href: str) -> str:
    source_line = f"<p><em>{_esc(item.get('source', ''))}</em></p>" if item.get("source") else ""
    summary = item.get("summary", "")
    summary_line = "" if text_utils.is_redundant_summary(item["title"], summary) else f"<p>{_esc(summary)}</p>"
    return (
        f"<h2>{_esc(item['title'])}</h2>"
        f"{source_line}"
        f"{summary_line}"
        f'<p><a href="{full_href}">Full article {FORWARD_ARROW}</a></p>'
        f"<hr/>"
        f'<p><a href="{landing_href}">{BACK_ARROW} Back</a></p>'
    )


def _full_html(item: dict, landing_href: str) -> str:
    body = _esc(item.get("text", "")).replace("\n", "<br/>")
    link_line = f'<p><a href="{_esc(item["url"])}">{_esc(item["url"])}</a></p>' if item.get("url") else ""
    return (
        f"<h2>{_esc(item['title'])}</h2>"
        f"<p>{body}</p>"
        f"{link_line}"
        f"<hr/>"
        f'<p><a href="{landing_href}">{BACK_ARROW} Back</a></p>'
    )


def _landing_html(heading: str, status_line: str | None, groups: list[tuple[str, list[tuple[str, str]]]], footer_html: str) -> str:
    parts = [f"<h1>{_esc(heading)}</h1>"]
    if status_line:
        parts.append(f'<p style="color:#900"><strong>{_esc(status_line)}</strong></p>')
    for section_name, entries in groups:
        if not entries:
            continue
        if section_name:
            parts.append(f"<h3>{_esc(section_name)}</h3>")
        parts.append("<ul>")
        for title, href in entries:
            parts.append(f'<li><a href="{href}">{_esc(title)}</a></li>')
        parts.append("</ul>")
    if footer_html:
        parts.append(f"<hr/>{footer_html}")
    return "".join(parts)


def _add_item_pages(book: epub.EpubBook, section_name: str, items: list[dict], landing_href: str, lang: str) -> tuple[list[tuple[str, str]], list]:
    """Create a TL;DR + full-article chapter pair per item. Returns
    (landing entries as (title, tldr_href), chapters in reading order)."""
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
    Expected keys: "World", "AI", "Chile" (main landing) and "Read Later"
    (second landing). status_line, if set, renders at the top of the main
    landing per PRD 5.10 failure handling.
    """
    book = epub.EpubBook()
    book.set_identifier(f"kindle-news-{edition_date}")
    book.set_title(f"News Digest — {edition_date}")
    book.set_language("en")

    read_later_items = sections.get("Read Later", [])

    news_groups = []
    news_chapters = []
    for section_name in NEWS_SECTIONS:
        entries, chapters = _add_item_pages(
            book, section_name, sections.get(section_name, []), LANDING_FILE, LANG_BY_SECTION[section_name]
        )
        news_groups.append((section_name, entries))
        news_chapters.extend(chapters)

    read_later_landing = None
    read_later_chapters = []
    if read_later_items:
        rl_entries, read_later_chapters = _add_item_pages(book, "Read Later", read_later_items, READ_LATER_LANDING_FILE, "en")
        rl_footer = f'<p><a href="{LANDING_FILE}">{BACK_ARROW} Main Digest</a></p>'
        read_later_landing = epub.EpubHtml(title="Read Later", file_name=READ_LATER_LANDING_FILE, lang="en")
        read_later_landing.content = _landing_html("Read Later", None, [("", rl_entries)], rl_footer)
        book.add_item(read_later_landing)

    main_footer = f'<p><a href="{READ_LATER_LANDING_FILE}">Read Later {FORWARD_ARROW}</a></p>' if read_later_landing else ""
    main_landing = epub.EpubHtml(title="News Digest", file_name=LANDING_FILE, lang="en")
    main_landing.content = _landing_html(f"News Digest — {edition_date}", status_line, news_groups, main_footer)
    book.add_item(main_landing)

    spine = [main_landing, *news_chapters]
    toc = [epub.Link(LANDING_FILE, "News Digest", "landing")]
    if read_later_landing:
        spine.extend([read_later_landing, *read_later_chapters])
        toc.append(epub.Link(READ_LATER_LANDING_FILE, "Read Later", "read_later_landing"))

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine + ["nav"]

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
