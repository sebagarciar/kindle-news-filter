"""Daily orchestrator. PRD 4, 5.10.

Run once in the afternoon (Madrid time), manually or via cron/launchd:

  1. Drain the Telegram inbox (telegram_bot.py) -> update preferences/queue
  2. Ingest RSS candidates per category (ingest.py)
  3. Apply exclusions (preferences.py)
  4. Cluster + rank World/AI (cluster.py), rank Chile directly (rank.py),
     checking each against the backlog (backlog.py, inside rank.py)
  5. Pull up to 5 read-later items (read_later.py)
  6. Fetch and embed full text for everything selected (fetch.py); a
     read-later item that's a YouTube link gets its transcript summarized
     instead (youtube.py) — there's no article text to extract from a video
  7. Build the EPUB (epub_builder.py)
  8. Send it (deliver.py)
  9. Record what was sent (backlog.py)

The edition must go out every day it runs, even in a degraded state — if a
source or fetch fails, that failure becomes a status line at the top of the
EPUB (e.g. "3 of 5 world sources failed"), not a skipped send. Silence is
the one unacceptable outcome. Failures are also logged locally.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

import backlog
import cluster
import deliver
import epub_builder
import fetch
import ingest
import preferences
import read_later
import rank
import telegram_bot
import youtube

# How many pre-ranked clusters get handed to the model per category — the
# model does the final selection of 3, this just bounds the prompt size.
CLUSTERS_TO_MODEL = 15


def _log(message: str) -> None:
    logging.info(message)


def _rank_clustered_category(category: str, candidates: list[dict], language: str, failures: list[str]) -> list[dict]:
    if not candidates:
        failures.append(f"{category}: no candidates (all sources failed)")
        return []
    clusters = cluster.rank_clusters(cluster.cluster_by_similarity(candidates))
    top_clusters = clusters[:CLUSTERS_TO_MODEL]
    reps = [c[0] for c in top_clusters]
    source_counts = {c[0]["title"]: len({item["source"] for item in c}) for c in top_clusters}
    try:
        return rank.select_top_three(reps, preferences.load_preferences(), category, language, source_counts)
    except Exception as e:
        failures.append(f"{category}: ranking failed ({e})")
        return []


def _rank_flat_category(category: str, candidates: list[dict], language: str, failures: list[str]) -> list[dict]:
    if not candidates:
        failures.append(f"{category}: no candidates (all sources failed)")
        return []
    try:
        return rank.select_top_three(candidates, preferences.load_preferences(), category, language)
    except Exception as e:
        failures.append(f"{category}: ranking failed ({e})")
        return []


def _embed(selected: list[dict], failures: list[str], label: str) -> list[dict]:
    """Fetch full text for each selected item, same fallback chain as read-later."""
    items = []
    for entry in selected:
        try:
            result = fetch.fetch_article_text(entry["url"], entry["summary"])
        except Exception as e:
            failures.append(f"{label}: fetch failed for '{entry['title'][:40]}' ({e})")
            result = {"text": entry["summary"], "truncated": False, "full_text_available": False}
        title = entry["title"] + (" (update)" if entry.get("is_update") else "")
        items.append({"title": title, "url": entry["url"], "summary": entry["summary"], "text": result["text"]})
    return items


def _embed_read_later(queued: list[dict], failures: list[str]) -> list[dict]:
    items = []
    for entry in queued:
        title = entry["text"][:80] or entry["url"] or "(untitled)"
        text = entry["text"]
        summary = entry["text"][:200]
        if entry["url"] and youtube.is_youtube_url(entry["url"]):
            try:
                result = youtube.fetch_video_summary(entry["url"], entry["text"])
                title = result["title"] or title
                text = result["text"]
                summary = text[:200]
            except Exception as e:
                failures.append(f"Read Later: video summary failed for '{title}' ({e})")
        elif entry["url"]:
            try:
                result = fetch.fetch_article_text(entry["url"], entry["text"])
                text = result["text"]
            except Exception as e:
                failures.append(f"Read Later: fetch failed for '{title}' ({e})")
        items.append({"title": title, "url": entry["url"], "summary": summary, "text": text})
    return items


def run() -> None:
    load_dotenv()
    state_dir = backlog.BACKLOG_PATH.parent
    state_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=state_dir / "run.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    failures: list[str] = []
    edition_date = datetime.now(tz=timezone.utc).astimezone().date().isoformat()

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if bot_token:
        try:
            telegram_bot.drain_inbox(bot_token)
        except Exception as e:
            failures.append(f"Telegram inbox: {e}")
            _log(f"Telegram drain failed: {e}")
    else:
        failures.append("Telegram: TELEGRAM_BOT_TOKEN not set, inbox not drained")

    exclusions = preferences.load_exclusions()

    world_raw, world_failed_sources = ingest.fetch_category(ingest.WORLD_FEEDS)
    ai_raw, ai_failed_sources = ingest.fetch_ai_candidates()
    chile_raw, chile_failed_sources = ingest.fetch_category(ingest.CHILE_FEEDS)
    for label, failed_sources in [("World", world_failed_sources), ("AI", ai_failed_sources), ("Chile", chile_failed_sources)]:
        if failed_sources:
            failures.append(f"{label}: {len(failed_sources)} source(s) failed ({', '.join(failed_sources)})")

    world_candidates = preferences.apply_exclusions(world_raw, exclusions)
    ai_candidates = preferences.apply_exclusions(ai_raw, exclusions)
    chile_candidates = preferences.apply_exclusions(chile_raw, exclusions)

    world_selected = _rank_clustered_category("World", world_candidates, "en", failures)
    ai_selected = _rank_clustered_category("AI", ai_candidates, "en", failures)
    chile_selected = _rank_flat_category("Chile", chile_candidates, "es", failures)

    read_later_queued = read_later.pop_for_edition()

    sections = {
        "World": _embed(world_selected, failures, "World"),
        "AI": _embed(ai_selected, failures, "AI"),
        "Chile": _embed(chile_selected, failures, "Chile"),
        "Read Later": _embed_read_later(read_later_queued, failures),
    }

    status_line = "; ".join(failures) if failures else None
    if failures:
        _log(f"Degraded run for {edition_date}: {status_line}")
    try:
        epub_bytes = epub_builder.build_epub(edition_date, sections, status_line)
    except Exception as e:
        _log(f"FATAL: EPUB build failed: {e}")
        raise

    output_dir = state_dir.parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"edition-{edition_date}.epub"
    output_path.write_bytes(epub_bytes)
    _log(f"Saved local copy: {output_path}")

    try:
        deliver.send_edition(epub_bytes, edition_date)
        _log(f"Sent edition for {edition_date} ({len(epub_bytes)} bytes). Status: {status_line}")
    except Exception as e:
        _log(f"FATAL: delivery failed: {e}")
        raise

    # Updates get recorded too, so the next repeat check sees the latest summary.
    for entry in world_selected + ai_selected + chile_selected:
        backlog.record(entry)


if __name__ == "__main__":
    run()
