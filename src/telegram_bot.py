"""Telegram inbox. PRD 5.5.

Polls getUpdates on each run and drains pending messages — no webhook, no
always-on process, stays laptop-local. Routing:

  starts with "prefer"  -> append to preferences file, reply with confirmation
  contains a URL         -> add to read-later queue with a timestamp
  plain text, no URL     -> standalone read-later item (the X-post path —
                             paid API and scraping are both non-starters, so
                             this relies on the phone share sheet carrying
                             post text + link in one message)

When an X post links to a real article, the underlying link should be used,
not the X one.
"""

from pathlib import Path

LAST_UPDATE_ID_PATH = Path(__file__).parent.parent / "state" / "last_update_id"


def poll_updates(bot_token: str) -> list[dict]:
    """Fetch pending messages since the last stored update_id."""
    raise NotImplementedError


def route_message(text: str) -> tuple[str, str]:
    """Classify a message as ("preference", text) | ("link", url) | ("note", text)."""
    raise NotImplementedError
