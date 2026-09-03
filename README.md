# Kindle News Filter

A local script that builds a daily EPUB news digest — nine ranked headlines
(world, AI, Chile) plus queued read-later articles from Telegram — and emails
it straight to a Kindle. Full spec in [`kindle-news-filter-prd.md`](kindle-news-filter-prd.md).

## Status

All modules are implemented, and everything that doesn't need a secret has
been tested against live sources: RSS ingestion (real feeds, verified this
session — see PRD section 8 for what changed), clustering, article
extraction and its fallback chain, and EPUB assembly all produce real
output today. A test edition built from live World headlines was sent and
opened successfully.

Not yet run end-to-end, because they need credentials this session doesn't
have:
- **Ranking** (`src/rank.py`) — calls the Anthropic API. Code follows the
  documented SDK usage but has never made a real call.
- **Telegram inbox** (`src/telegram_bot.py`) — needs a BotFather token.
  Message routing logic is unit-tested; the live poll/reply round-trip isn't.
- **Delivery** (`src/deliver.py`) — needs SMTP credentials and the sending
  address on Amazon's approved sender list.

Next step: fill in `.env`, then run `python src/main.py` once manually and
read the result on the actual Kindle (PRD section 7, setup checklist).

## Setup

1. `python3 -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. `cp .env.example .env` and fill in the values (bot token, SMTP creds, API key, Kindle address)
4. Add the sending email to your Amazon approved sender list
5. Verify every RSS feed in `src/ingest.py` actually resolves, La Tercera especially

## Run

```bash
python src/main.py
```

Intended to run once daily via cron/launchd, afternoon Madrid time (see PRD section 4).

## State

Runtime files live in `state/` and are gitignored — they're personal data, not
code. See PRD section 6 for what each one holds. `config/` holds the starter
templates for `preferences.txt` and `exclusions.txt`, copied into `state/` on
first run.
