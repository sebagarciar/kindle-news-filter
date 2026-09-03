"""Daily orchestrator. PRD 4, 5.10.

Run once in the afternoon (Madrid time), manually or via cron/launchd:

  1. Drain the Telegram inbox (telegram_bot.py) -> update preferences/queue
  2. Ingest RSS candidates per category (ingest.py)
  3. Apply exclusions (preferences.py)
  4. Cluster + rank World/AI (cluster.py), rank Chile directly (rank.py),
     checking each against the backlog (backlog.py)
  5. Pull up to 5 read-later items (queue.py)
  6. Fetch and embed full text for everything selected (fetch.py)
  7. Build the EPUB (epub_builder.py)
  8. Send it (deliver.py)
  9. Record what was sent (backlog.py)

The edition must go out every day it runs, even in a degraded state — if a
source or fetch fails, that failure becomes a status line at the top of the
EPUB (e.g. "3 of 5 world sources failed"), not a skipped send. Silence is
the one unacceptable outcome. Failures are also logged locally.
"""


def run() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    run()
