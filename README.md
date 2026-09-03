# Kindle News Filter

A local script that builds a daily EPUB news digest — nine ranked headlines
(world, AI, Chile) plus queued read-later articles from Telegram — and emails
it straight to a Kindle. Full spec in [`kindle-news-filter-prd.md`](kindle-news-filter-prd.md).

Status: scaffolding only. No ranking, fetching, or delivery logic yet — see
`src/` for stubs mapped to each PRD section.

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
