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
   so it gets its transcript pulled and turned into reading notes by the
   same local model instead — same no-cloud rule, same graceful fallback to
   a "watch it here" link if the video has no transcript. A transcript
   longer than the model can hold at once is read in chunks and the notes
   merged, so they cover the end of a talk and not just its first ten
   minutes.
5. **Build the EPUB**: one landing page with four sections — World, AI,
   Chile, Read Later — each a heading with its headlines underneath. Tap a
   title for a TL;DR page, tap that for the full article; each links back
   to its own section on the landing page, not the top of it. Every
   headline is also its own chapter in the EPUB's table of contents, so a
   Kindle's "time left in chapter" shows reading time per headline instead
   of for the whole edition.
6. **Deliver**: email the EPUB to the Kindle's send-to-Kindle address.

A message to the Telegram bot starting with "prefer" tunes the ranking
prompt (e.g. "less football"); any other message with a link queues it as
a read-later item, capped at 5 per edition with the rest rolling over.

## Status (as of 2026-09-05)

Every stage has run against live data, not test fixtures: real RSS feeds,
real cross-source clustering on the day's actual headlines, real ranking
and summarizing through the local model, real article extraction
including its paywall and dead-link fallbacks, and end-to-end sends that
landed on the actual Kindle. A real Telegram message has been drained
into the read-later queue and delivered in the same edition.

Seven issues surfaced only because of that live testing, not code review:

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
- **A feed that only answers a browser.** VentureBeat's AI feed kept
  failing: it sits behind bot protection that returns HTTP 429 and an
  HTML challenge page to a plain feed reader. It does respond to a spoofed
  desktop-browser User-Agent, which would have been the quick fix and the
  wrong one, since it makes the digest depend on staying undetected.
  Swapped for Ars Technica's AI section, feed and extraction both verified.
- **The ranking prompt was summarising from titles alone.** Two of three
  Chile summaries shipped blank on 2026-09-04. The model was writing them,
  and the redundancy guard in `epub_builder.py` was correctly deleting
  them, because they only reworded the headline. The cause was upstream:
  `rank.py` passed the model a title, URL and source but dropped the RSS
  excerpt, so on local Chilean stories it has no background knowledge of,
  rewording was the only thing left to do. The excerpt is now part of the
  prompt, and a summary that still comes back redundant falls back to the
  excerpt's own opening sentence rather than to nothing. Excerpt handling
  is block-aware for that reason: flattening an RSS fragment to one line
  splices the newsletter sign-up box into the middle of the summary.

- **The read-later queue emptied before the edition existed.** A queued
  YouTube video shipped in the first edition of 2026-09-04 and was missing
  from the two re-runs that followed that evening, including the copy saved
  to `output/`. Picking items for an edition deleted them on the spot,
  before the EPUB was built or sent, so a re-run — or any crash between
  picking and sending — lost them with nothing left on disk to rebuild
  from. Items are now stamped as delivered only after the send succeeds,
  and a re-run on the same date rebuilds the identical section. Nothing
  failed and nothing was logged; the item simply wasn't there, which is why
  it took reading the run log against the queue's timestamps to find.
- **Summaries too short to learn anything from.** The first version of the
  video path asked for 3-5 sentences over the first 12,000 characters of
  transcript, which is a blurb about the first third of a talk. A video
  gets queued because it's worth an hour of attention, so the notes now run
  500-900 words across the whole transcript, and the prompt asks for the
  teachable substance by name (methods, rules of thumb, mistakes,
  recommendations) while forbidding it where the video doesn't offer it. A
  related trap sat underneath: Ollama's default context window is a few
  thousand tokens and it truncates a longer prompt silently, so half a
  transcript can go missing with no error anywhere. Long-context calls now
  set `num_ctx` explicitly.

Repeat detection has now been watched doing its job: a story that went out
in one edition was still sitting live in the feed for the next one and was
correctly held back, rather than going out twice.

Reading real editions on the device surfaced four navigation/content
complaints, fixed on 2026-09-05: the separate Read Later page got folded
into the main landing as a fourth section; "Back" links now jump to an
item's own section instead of the top of the landing page; extracted
article text now gets a boilerplate pass (comment counters, "click here to
subscribe", related-reading blocks) that `trafilatura` sometimes leaves
behind; and the ranking prompt can now leave a summary blank when the title
already says everything, instead of rewording it. Each headline is also
now its own chapter, so a Kindle's time-left-in-chapter reflects one
headline instead of the whole edition. Verified by rebuilding a real
edition and checking its markup directly — not yet re-read on the device.

Not yet done: the daily cron job isn't scheduled, so this is still started
by hand.

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

A queued YouTube link adds real time to the run: roughly five minutes of
local inference for a 40-minute video, since the transcript is read in
chunks and then merged. Five queued videos is the worst case the
per-edition cap allows, and that run takes most of half an hour.

Intended to run once daily via cron/launchd, afternoon Madrid time (see PRD section 4).

## State

Runtime files live in `state/` and are gitignored. They're personal data, not
code. See PRD section 6 for what each one holds. `config/` holds the starter
templates for `preferences.txt` and `exclusions.txt`, copied into `state/` on
first run. Each built edition is also saved to `output/` (gitignored).
