# Kindle News Filter

A local script that builds a daily EPUB news digest — nine ranked headlines
(world, AI, Chile) plus queued read-later articles from Telegram — and emails
it straight to a Kindle. Full spec in [`kindle-news-filter-prd.md`](kindle-news-filter-prd.md).

Ranking and summarizing run on a local model via [Ollama](https://ollama.com)
— no API key, nothing leaves the laptop. Everything else was already local
(RSS, article text, EPUB, email).

## Status

All modules are implemented and tested against live sources this session:
real RSS feeds, real clustering on the day's actual headlines, real ranking
+ summarizing through a local Ollama model (both the World/AI clustered
path and the Chile flat-list path, in English and Spanish), real article
extraction with its fallback chain, and a real EPUB — built, sent, and
opened successfully.

Not yet run end-to-end, because they need credentials this session doesn't
have:
- **Telegram inbox** (`src/telegram_bot.py`) — needs a BotFather token.
  Message routing logic is unit-tested; the live poll/reply round-trip isn't.
- **Delivery** (`src/deliver.py`) — needs SMTP credentials and the sending
  address on Amazon's approved sender list.

Next step: fill in `.env`, then run `python src/main.py` once manually and
read the result on the actual Kindle (PRD section 7, setup checklist).

## Setup

1. Install [Ollama](https://ollama.com) and pull a model: `ollama pull llama3.1:8b` (or point `OLLAMA_MODEL` in `.env` at any model you already have — `ollama list` shows what's pulled)
2. `python3 -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. `cp .env.example .env` and fill in the values (bot token, SMTP creds, Kindle address)
5. Add the sending email to your Amazon approved sender list
6. Verify every RSS feed in `src/ingest.py` still resolves — feeds go stale over time; Emol's already turned out to be dead once (see PRD section 8)

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
