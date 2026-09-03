"""EPUB assembly. PRD 5.8.

Structure: title page with edition date, a table of contents listing all
nine headlines plus read-later items (each with its summary), section order
World -> AI -> Chile -> Read Later. Each TOC entry links down to the full
text in the same file.

Also owns the total-size check against Amazon's send-to-Kindle email limit
(PRD 5.4) — articles get truncated here if the running total risks it.
"""


def build_epub(edition_date: str, sections: dict[str, list[dict]], status_line: str | None) -> bytes:
    """Assemble the day's edition into EPUB bytes.

    status_line, if set, renders at the top per PRD 5.10 failure handling.
    """
    raise NotImplementedError
