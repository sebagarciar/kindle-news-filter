"""EPUB assembly. PRD 5.8, revised after live testing and a design review.

Tap-through structure:

  Main landing (World / AI / Chile / Read Later, each a section label with
    its headlines underneath, and under each headline one small line: the
    source, "+N" for how many other sources covered it, and minutes to read)
    -> tap a title -> the story page: section and source line, headline,
       the TL;DR in italics as a standfirst (omitted when it's redundant with
       the title, see text_utils.is_redundant_summary), then the full text
    -> at the end of the story: "Read on bbc.co.uk", "Next: <title>" and
       "Back to World", which jumps to that story's own section on the
       landing page (an in-page anchor), not to the top of it.

The TL;DR used to be a page of its own between the landing and the article.
Folded into the top of the article after the design review: on e-ink each
page is a slow full refresh, and two lines of summary didn't earn one.
Read Later likewise used to get its own second landing page, and was folded
into the main one as a fourth section.

Every story is its own chapter in the EPUB's nav/NCX (nested under its
section). That's what turns on a Kindle's "time left in chapter" estimate
per story instead of for the whole edition. The nav page itself is kept out
of the reading order, so paging on past the last story doesn't land on a
raw contents list.

Styling is one small stylesheet. It never sets a font family or a base font
size, so the Kindle's own font and size settings keep working; sizes are in
em, relative to whatever the reader picked.

Still owns the total-size check against Amazon's send-to-Kindle email limit
(PRD 5.4, 5.10): if the assembled book is still too big after fetch.py's
per-article truncation, that should be caught here rather than letting
delivery fail silently.
"""

from __future__ import annotations

import html
import os
import re
import tempfile
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ebooklib import epub

import text_utils

# Send-to-Kindle's documented email/attachment limit is 50MB; staying well
# under it leaves room for MIME/base64 overhead in deliver.py.
MAX_EPUB_BYTES = 40 * 1024 * 1024

SECTIONS = ["World", "AI", "Chile", "Read Later"]
LANG_BY_SECTION = {"World": "en", "AI": "en", "Chile": "es", "Read Later": "en"}

LANDING_FILE = "index.xhtml"
STYLE_FILE = "style.css"

BACK_ARROW = "←"
FORWARD_ARROW = "→"
DOT = " · "

# Reading speed for the "4 min" estimate. Kindle's own chapter estimate
# learns the reader's speed; this only has to rank stories against each
# other on the landing page.
WORDS_PER_MINUTE = 230

# Feed names carry the category ("BBC World", "TechCrunch AI") because
# ingest.py keeps one feed per category. Under a "World" heading that
# suffix is noise.
_SOURCE_SUFFIX_RE = re.compile(r"\s+(?:World|AI)$")

# The Guardian's live blogs end their title in " - live". Shown as a label
# instead, so the headline reads as a headline.
_LIVE_SUFFIX_RE = re.compile(r"\s+[-–]\s+live$", re.I)

# Query parameters that only tell the publisher which feed a click came
# from. Dropped from the printed link; anything else in the query is kept.
_TRACKING_PARAM_RE = re.compile(r"^(?:utm_|at_)|^(?:traffic_source|ref|cmpid|ns_mchannel|ns_source)$", re.I)

# Editorial notes fetch.py adds to the text ("[Article cut here: ...]").
_NOTE_RE = re.compile(r"^\[.*\]$", re.S)

STYLESHEET = """
h1, h2, p { margin: 0; }
a { text-decoration: none; color: inherit; }
/* Kindle justifies by default. Fine for article text, but it stretches
   short headline and label lines into wide gaps. */
h1, h2, .story p, .kicker, .standfirst, .endnav p { text-align: left; }

.masthead { margin-bottom: 0.8em; padding-bottom: 0.4em; border-bottom: 2px solid #000; }
.masthead h1 { font-size: 1.6em; font-weight: bold; line-height: 1.15; }
.dateline { margin-top: 0.2em; font-size: 0.8em; color: #444; }
.status { margin: 0.6em 0 0.2em 0; padding: 0.4em 0.6em; border: 1px solid #000; font-size: 0.85em; }

h2.section { margin-top: 1.3em; padding-bottom: 0.15em; border-bottom: 1px solid #777;
  font-size: 0.75em; font-weight: bold; text-transform: uppercase; letter-spacing: 0.1em; }
.story { margin-top: 0.75em; }
.story .title { font-weight: bold; line-height: 1.25; }
.meta { margin-top: 0.1em; font-size: 0.75em; color: #444; }

.kicker { margin-bottom: 0.5em; font-size: 0.75em; color: #444;
  text-transform: uppercase; letter-spacing: 0.08em; }
h1.headline { margin-bottom: 0.6em; font-size: 1.45em; font-weight: bold; line-height: 1.2; }
.standfirst { margin-bottom: 1.1em; padding-left: 0.6em; border-left: 2px solid #000; font-style: italic; }
.body p { text-indent: 1.2em; }
.body p.first { text-indent: 0; }
.body p.note { margin-top: 0.8em; text-indent: 0; font-size: 0.85em; font-style: italic; color: #444; }

.endnav { margin-top: 1.6em; padding-top: 0.5em; border-top: 1px solid #777; font-size: 0.85em; }
.endnav p { margin-top: 0.5em; }
.endnav .next { font-weight: bold; }
"""


def _esc(text: str) -> str:
    return html.escape(text or "")


def _slug(section_name: str, i: int) -> str:
    return f"{section_name.lower().replace(' ', '_')}_{i}"


def _section_anchor(section_name: str) -> str:
    return section_name.lower().replace(" ", "_")


def _human_date(edition_date: str) -> str:
    """"2026-10-19" -> "Monday 19 October 2026"."""
    try:
        d = date.fromisoformat(edition_date)
    except ValueError:
        return edition_date
    return f"{d:%A} {d.day} {d:%B %Y}"


def _short_date(edition_date: str) -> str:
    try:
        d = date.fromisoformat(edition_date)
    except ValueError:
        return edition_date
    return f"{d.day} {d:%b %Y}"


def _domain(url: str) -> str:
    host = urlsplit(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _clean_url(url: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING_PARAM_RE.search(k)]
    return urlunsplit(parts._replace(query=urlencode(query)))


def _source_label(item: dict) -> str:
    """"BBC +4": the main source, and how many others covered the story.
    Read Later items have no feed, so they show the site's domain."""
    source = _SOURCE_SUFFIX_RE.sub("", item.get("source") or "") or _domain(item.get("url", ""))
    others = (item.get("source_count") or 1) - 1
    return f"{source} +{others}" if source and others > 0 else source


def _minutes(text: str) -> int:
    return max(1, round(len((text or "").split()) / WORDS_PER_MINUTE))


def _story(item: dict, section_name: str) -> dict:
    """Everything the landing line and the story page show, worked out once."""
    title = item["title"]
    live = bool(_LIVE_SUFFIX_RE.search(title))
    title = _LIVE_SUFFIX_RE.sub("", title)
    labels = [label for label, on in (("Update", item.get("is_update")), ("Live", live)) if on]
    minutes = _minutes(item.get("text", ""))
    meta = [*labels, _source_label(item), f"{minutes} min"]
    return {
        "title": title,
        "meta": DOT.join(part for part in meta if part),
        "kicker": DOT.join(part for part in [section_name, *meta] if part),
        "minutes": minutes,
    }


def _same_text(a: str, b: str) -> bool:
    normalise = lambda s: re.sub(r"\W+", " ", (s or "").lower()).strip()
    return bool(normalise(a)) and normalise(a) == normalise(b)


def _body_html(text: str, repeats: list[str]) -> str:
    """Blank-line-separated blocks become real paragraphs, single newlines
    stay line breaks inside one (the video notes use those for lists).

    Blocks that repeat the headline or the standfirst are dropped: most
    sites print both again at the top of the article body, so the reader
    read the title twice before the story started. So is any block the
    article itself repeats. repeats holds the headline (as fed and as
    shown) and the standfirst, if one is shown.
    """
    seen = [r for r in repeats if r]
    parts = []
    first = True
    for raw in (text or "").split("\n\n"):
        block = raw.strip()
        if not block or any(_same_text(block, s) for s in seen):
            continue
        seen.append(block)
        content = _esc(block).replace("\n", "<br/>")
        if _NOTE_RE.match(block):
            parts.append(f'<p class="note">{content}</p>')
        else:
            parts.append(f'<p class="first">{content}</p>' if first else f"<p>{content}</p>")
            first = False
    return "".join(parts)


def _story_html(item: dict, story: dict, section_name: str, next_story: tuple[str, str] | None) -> str:
    summary = item.get("summary", "")
    show_summary = bool(summary) and not text_utils.is_redundant_summary(story["title"], summary)
    standfirst = f'<p class="standfirst">{_esc(summary)}</p>' if show_summary else ""
    body = _body_html(item.get("text", ""), [item["title"], story["title"], summary if show_summary else ""])

    links = []
    if item.get("url"):
        links.append(f'<p><a href="{_esc(_clean_url(item["url"]))}">Read on {_esc(_domain(item["url"]))}</a></p>')
    if next_story:
        next_title, next_href = next_story
        links.append(f'<p class="next"><a href="{next_href}">Next: {_esc(next_title)} {FORWARD_ARROW}</a></p>')
    else:
        links.append("<p>End of this edition.</p>")
    links.append(f'<p><a href="{LANDING_FILE}#{_section_anchor(section_name)}">{BACK_ARROW} Back to {_esc(section_name)}</a></p>')

    return (
        f'<p class="kicker">{_esc(story["kicker"])}</p>'
        f'<h1 class="headline">{_esc(story["title"])}</h1>'
        f"{standfirst}"
        f'<div class="body">{body}</div>'
        f'<div class="endnav">{"".join(links)}</div>'
    )


def _landing_html(heading: str, dateline: str, status_line: str | None, groups: list[tuple[str, list[tuple[dict, str]]]]) -> str:
    parts = [f'<div class="masthead"><h1>{_esc(heading)}</h1><p class="dateline">{_esc(dateline)}</p></div>']
    if status_line:
        parts.append(f'<p class="status"><strong>Note:</strong> {_esc(status_line)}</p>')
    for section_name, entries in groups:
        if not entries:
            continue
        parts.append(f'<h2 class="section" id="{_section_anchor(section_name)}">{_esc(section_name)}</h2>')
        for story, href in entries:
            parts.append(
                f'<div class="story"><p class="title"><a href="{href}">{_esc(story["title"])}</a></p>'
                f'<p class="meta">{_esc(story["meta"])}</p></div>'
            )
    return "".join(parts)


def build_epub(
    edition_date: str,
    sections: dict[str, list[dict]],
    status_line: str | None,
    heading: str | None = None,
) -> bytes:
    """Assemble the day's edition into EPUB bytes.

    sections maps section name -> list of items, each with at least
    'title', 'summary', 'text'; 'source', 'source_count', 'url',
    'is_update' are optional. Expected keys: "World", "AI", "Chile",
    "Read Later", all on one landing page in that order (PRD 5.8).
    status_line, if set, renders at the top per PRD 5.10 failure handling.
    heading overrides the book title and landing headline, for an edition
    that isn't the daily digest (a one-off built from a handful of links,
    say), which shouldn't sit on the Kindle under the same name as the
    dailies.
    """
    masthead = heading or "News Digest"
    book_title = heading or f"News Digest {_short_date(edition_date)}"
    book = epub.EpubBook()
    book.set_identifier(f"kindle-news-{edition_date}")
    book.set_title(book_title)
    book.set_language("en")
    book.add_author("Kindle News")

    style = epub.EpubItem(uid="style", file_name=STYLE_FILE, media_type="text/css", content=STYLESHEET)
    book.add_item(style)

    # Work out every story first: each page links to the next one, which
    # may sit in the following section.
    planned = []
    for section_name in SECTIONS:
        for i, item in enumerate(sections.get(section_name, [])):
            planned.append((section_name, item, _story(item, section_name), f"{_slug(section_name, i)}.xhtml"))

    groups = {name: [] for name in SECTIONS}
    chapters = []
    for n, (section_name, item, story, file_name) in enumerate(planned):
        next_story = (planned[n + 1][2]["title"], planned[n + 1][3]) if n + 1 < len(planned) else None
        chapter = epub.EpubHtml(title=story["title"], file_name=file_name, lang=LANG_BY_SECTION[section_name])
        chapter.content = _story_html(item, story, section_name, next_story)
        chapter.add_item(style)
        book.add_item(chapter)
        chapters.append(chapter)
        groups[section_name].append((story, file_name))

    total_minutes = sum(story["minutes"] for _, _, story, _ in planned)
    count = len(planned)
    dateline = DOT.join([
        _human_date(edition_date),
        f"{count} {'story' if count == 1 else 'stories'}",
        f"about {total_minutes} min",
    ])

    toc = [epub.Link(LANDING_FILE, masthead, "landing")]
    for section_name in SECTIONS:
        entries = groups[section_name]
        if entries:
            anchor = _section_anchor(section_name)
            section_links = [epub.Link(href, story["title"], f"{anchor}_{i}") for i, (story, href) in enumerate(entries)]
            toc.append((epub.Section(section_name), section_links))

    main_landing = epub.EpubHtml(title=masthead, file_name=LANDING_FILE, lang="en")
    main_landing.content = _landing_html(masthead, dateline, status_line, [(name, groups[name]) for name in SECTIONS])
    main_landing.add_item(style)
    book.add_item(main_landing)

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = [main_landing, *chapters, ("nav", "no")]

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
            "budget even after per-article truncation. Reduce TRUNCATE_CHARS in fetch.py."
        )
    return data
