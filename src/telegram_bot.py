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
not the X one — left as a manual habit (paste the article link, not the X
link) rather than auto-detected, since reliably telling "X post that links
out" from "X post that's the whole story" from text alone isn't robust.

Untested against a real bot — needs a BotFather token this session doesn't
have. The Bot API shape here (getUpdates, offset, long-poll) is stable and
well-documented; confirm one real round-trip before relying on it.
"""

from __future__ import annotations

import re
from pathlib import Path

import requests

import preferences
import read_later

_URL_RE = re.compile(r"https?://\S+")
_TIMEOUT = 20  # getUpdates long-polls; keep this above Telegram's own poll window
LAST_UPDATE_ID_PATH = Path(__file__).parent.parent / "state" / "last_update_id"


def _load_last_update_id() -> int | None:
    if not LAST_UPDATE_ID_PATH.exists():
        return None
    content = LAST_UPDATE_ID_PATH.read_text().strip()
    return int(content) if content else None


def _save_last_update_id(update_id: int) -> None:
    LAST_UPDATE_ID_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_UPDATE_ID_PATH.write_text(str(update_id))


def poll_updates(bot_token: str) -> list[dict]:
    """Fetch pending messages since the last stored update_id, then advance
    the offset past them so they aren't redelivered next run."""
    offset = _load_last_update_id()
    params = {"timeout": 0}
    if offset is not None:
        params["offset"] = offset + 1

    response = requests.get(
        f"https://api.telegram.org/bot{bot_token}/getUpdates",
        params=params,
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    result = response.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram getUpdates failed: {result}")

    updates = result["result"]
    if updates:
        _save_last_update_id(updates[-1]["update_id"])
    return updates


def route_message(text: str) -> tuple[str, str]:
    """Classify a message as ("preference", text) | ("link", url) | ("note", text)."""
    stripped = text.strip()
    if stripped.lower().startswith("prefer"):
        return "preference", stripped[len("prefer"):].lstrip(" :").strip()
    url_match = _URL_RE.search(stripped)
    if url_match:
        return "link", url_match.group(0)
    return "note", stripped


def _reply(bot_token: str, chat_id: int, text: str) -> None:
    requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=_TIMEOUT,
    )


def drain_inbox(bot_token: str) -> None:
    """PRD 5.5 end to end: poll, route each message, act, and confirm
    preference updates back to the sender."""
    for update in poll_updates(bot_token):
        message = update.get("message")
        if not message or "text" not in message:
            continue
        chat_id = message["chat"]["id"]
        kind, payload = route_message(message["text"])

        if kind == "preference":
            preferences.append_preference(payload)
            _reply(bot_token, chat_id, f"Preference added: {payload}")
        elif kind == "link":
            read_later.add({"url": payload, "text": message["text"]})
        else:
            read_later.add({"url": "", "text": payload})
