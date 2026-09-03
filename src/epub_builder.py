"""EPUB assembly. PRD 5.8.

Structure: title page with edition date, a table of contents listing all
nine headlines plus read-later items (each with its summary), section order
World -> AI -> Chile -> Read Later. Each TOC entry links down to the full
text in the same file.

Also owns the total-size check against Amazon's send-to-Kindle email limit
(PRD 5.4, 5.10) — if the assembled book is still too big after fetch.py's
per-article truncation, sections get trimmed here with a status note rather
than letting delivery fail silently.
"""

from __future__ import annotations

import html
import os
import tempfile

from ebooklib import epub

# Send-to-Kindle's documented email/attachment limit is 50MB; staying well
# under it leaves room for MIME/base64 overhead in deliver.py.
MAX_EPUB_BYTES = 40 * 1024 * 1024

SECTION_ORDER = ["World", "AI", "Chile", "Read Later"]


def _esc(text: str) -> str:
    return html.escape(text or "")


def _chapter_html(item: dict) -> str:
    body = _esc(item.get("text", item.get("summary", ""))).replace("\n", "<br/>")
    source_line = f"<p><em>{_esc(item.get('source', ''))}</em></p>" if item.get("source") else ""
    link_line = f'<p><a href="{_esc(item["url"])}">{_esc(item["url"])}</a></p>' if item.get("url") else ""
    return f"<h2>{_esc(item['title'])}</h2>{source_line}<p>{_esc(item.get('summary', ''))}</p><hr/><p>{body}</p>{link_line}"


def build_epub(edition_date: str, sections: dict[str, list[dict]], status_line: str | None) -> bytes:
    """Assemble the day's edition into EPUB bytes.

    sections maps section name (SECTION_ORDER) -> list of items, each with
    at least 'title', 'summary', 'text'; 'source' and 'url' are optional.
    status_line, if set, renders at the top per PRD 5.10 failure handling.
    """
    book = epub.EpubBook()
    book.set_identifier(f"kindle-news-{edition_date}")
    book.set_title(f"News Digest — {edition_date}")
    book.set_language("en")

    title_page_body = f"<h1>News Digest</h1><h3>{_esc(edition_date)}</h3>"
    if status_line:
        title_page_body += f'<p style="color:#900"><strong>{_esc(status_line)}</strong></p>'
    title_page = epub.EpubHtml(title="Title Page", file_name="title.xhtml", lang="en")
    title_page.content = title_page_body
    book.add_item(title_page)

    spine = [title_page]
    toc = []

    for section_name in SECTION_ORDER:
        items = sections.get(section_name, [])
        if not items:
            continue
        section_chapters = []
        for i, item in enumerate(items):
            chapter = epub.EpubHtml(
                title=item["title"],
                file_name=f"{section_name.lower().replace(' ', '_')}_{i}.xhtml",
                lang="en",
            )
            chapter.content = _chapter_html(item)
            book.add_item(chapter)
            spine.append(chapter)
            section_chapters.append(chapter)
        toc.append((epub.Section(section_name), section_chapters))

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
