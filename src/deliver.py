"""Delivery. PRD 5.9.

Emails the EPUB to the Kindle address. The sending address must already be
on the Amazon approved sender list — if it isn't, delivery fails silently
and everything upstream will look fine. Verify this first, per the setup
checklist (PRD 7).

Untested against a real mailbox — needs SMTP credentials this session
doesn't have. The MIME/smtplib usage itself is standard library, not
something that tends to drift, but confirm one real send before relying on
this for the daily run.
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def send_edition(epub_bytes: bytes, edition_date: str) -> None:
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_password = os.environ["SMTP_PASSWORD"]
    sender = os.environ["SENDER_EMAIL"]
    kindle_email = os.environ["KINDLE_EMAIL"]

    message = EmailMessage()
    message["From"] = sender
    message["To"] = kindle_email
    message["Subject"] = f"News Digest {edition_date}"
    message.set_content(f"News digest for {edition_date}. See attached EPUB.")
    message.add_attachment(
        epub_bytes,
        maintype="application",
        subtype="epub+zip",
        filename=f"news-digest-{edition_date}.epub",
    )

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(message)
