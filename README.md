# Kindle News Filter

A daily news digest, built and shipped by a script. It reads 12 RSS feeds
across World, AI, and Chile news, ranks headlines by cross-source
agreement, summarizes them with a local language model, and emails the
result as an EPUB to my Kindle. A Telegram bot lets me queue articles
(including X posts) from my phone for the same digest.

No cloud AI API, no server, no database. Everything runs on my laptop.

## Why

I wanted one offline-readable digest a day, not a feed to scroll. Nine
headlines, chosen for importance, not recency. Full spec in
[`kindle-news-filter-prd.md`](kindle-news-filter-prd.md).

## How it works

1. **Ingest**: pull recent headlines from 4 World feeds (BBC, Guardian,
   NPR, Al Jazeera), 5 AI sources (OpenAI, TechCrunch, The Verge,
   VentureBeat, Hacker News filtered by keyword), and 3 Chile feeds
   (Cooperativa, BioBioChile, La Tercera). Capped per feed to keep any one
   high-frequency source from crowding out the rest, about 30-40 candidates
   per category.
2. **Rank**: for World and AI, group headlines by similarity and treat
   stories covered by more outlets as more important, since RSS carries no
   popularity signal on its own. Chile's source pool is too small for that
   to mean anything, so those headlines go straight to the model instead.
3. **Select and summarize**: one local model call per category (Llama 3.1
   8B via [Ollama](https://ollama.com), no API key, nothing leaves the
   laptop) picks the top 3 and writes a 1-2 sentence summary each, in
   English for World/AI and Spanish for Chile. A 7-day backlog stops the
   same story from repeating unless it has genuinely developed, in which
   case it's reframed as an update.
4. **Fetch full text**: extract clean article text for each selected
   headline. If extraction fails or the source is paywalled, fall back to
   the RSS excerpt, then to a marked "full text unavailable" link. A
   read-later item that's a YouTube link has no article text to extract,
   so it gets its transcript pulled and summarized by the same local model
   instead — same no-cloud rule, same graceful fallback to a "watch it
   here" link if the video has no transcript.
5. **Build the EPUB**: a landing page listing the 9 headlines, each linking
   to a summary page, which links to the full article, which links back.
   Read-later items from Telegram get a second landing page, so a phone
   link-dump never buries the day's actual news.
6. **Deliver**: email the EPUB to the Kindle's send-to-Kindle address.

A message to the Telegram bot starting with "prefer" tunes the ranking
prompt (e.g. "less football"); any other message with a link queues it as
a read-later item, capped at 5 per edition with the rest rolling over.

## Status (as of 2026-09-03)

Every stage has run against live data, not test fixtures: real RSS feeds,
real cross-source clustering on the day's actual headlines, real ranking
and summarizing through the local model, real article extraction
including its paywall and dead-link fallbacks, and 3 real end-to-end
sends, each one landing on the actual Kindle. One of those runs also
drained a real Telegram message into the read-later queue and delivered
it in the same edition.

Three issues surfaced only because of that live testing, not code review:

- **A dependency I trusted was wrong.** The PRD assumed Emol's RSS feed
  worked. It's been discontinued; every documented URL now redirects to
  their plain HTML page. Caught by curl-testing every feed before wiring
  it in, not by reading Emol's docs.
- **A naming collision broke a third-party library.** A module I named
  `queue.py` shadowed Python's own `queue` module, which
  `trafilatura`'s dependencies import internally. The import failed with
  an unrelated-looking error three layers deep. Renamed to `read_later.py`.
- **NYT consistently blocked article extraction.** Every real edition
  hit a 403 fetching the selected NYT story, so that headline always fell
  back to a bare "read the original" link the reader still couldn't open
  (NYT itself blocks it). Swapped NYT for NPR World, whose RSS and article
  pages both extract cleanly.

Not yet done: the daily cron job isn't scheduled (still run manually), and
the 7-day repeat-detection logic hasn't been observed across an actual
multi-day run.

## Stack

Python. `feedparser` (RSS), `trafilatura` (article extraction), `ebooklib`
(EPUB), `requests` (Telegram Bot API), `smtplib` (email), Ollama (local
LLM inference).

## Setup

1. Install [Ollama](https://ollama.com) and pull a model: `ollama pull llama3.1:8b` (or point `OLLAMA_MODEL` in `.env` at any model you already have; `ollama list` shows what's pulled)
2. `python3 -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. `cp .env.example .env` and fill in the values (bot token, SMTP creds, Kindle address)
5. Add the sending email to your Amazon approved sender list
6. Verify every RSS feed in `src/ingest.py` still resolves. Feeds go stale over time; Emol's already turned out to be dead once (see PRD section 8)

## Run

```bash
python src/main.py
```

Intended to run once daily via cron/launchd, afternoon Madrid time (see PRD section 4).

## State

Runtime files live in `state/` and are gitignored. They're personal data, not
code. See PRD section 6 for what each one holds. `config/` holds the starter
templates for `preferences.txt` and `exclusions.txt`, copied into `state/` on
first run. Each built edition is also saved to `output/` (gitignored).
