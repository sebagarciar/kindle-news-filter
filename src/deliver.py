"""Delivery. PRD 5.9.

Emails the EPUB to the Kindle address. The sending address must already be
on the Amazon approved sender list — if it isn't, delivery fails silently
and everything upstream will look fine. Verify this first, per the setup
checklist (PRD 7).
"""


def send_edition(epub_bytes: bytes, edition_date: str) -> None:
    raise NotImplementedError
