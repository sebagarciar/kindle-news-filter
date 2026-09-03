# Kindle News Filter: Product Requirements

## 1. Summary

A local script that builds a daily EPUB news digest and emails it to a Kindle. Each edition contains nine ranked headlines (three world, three AI, three Chile) plus up to five read-later articles queued from Telegram. All article text is embedded so the digest reads fully offline.

## 2. Goals

- One file per day, readable end to end on the Kindle with no browser
- Signal over volume: nine items chosen for importance, not recency
- Steerable from the phone, with no code edits needed to change what gets surfaced
- Never fails silently

## 3. Non-goals

- No server, no hosting, no database. Runs on the laptop.
- No X/Twitter scraping. This was removed from a previous version for fragility and is not coming back.
- No web UI.
- Not a real-time alerting system. One edition per day.

## 4. Runtime

Single Python script, run in the afternoon (Madrid time) either manually or via cron/launchd. The afternoon slot matters: it means the Chilean news day is already well underway, so the Chile section is same-day rather than a stale overnight snapshot.

## 5. Functional requirements

### 5.1 Source ingestion

RSS only. Target 30 to 40 candidate headlines per category before ranking.

- **World**: 4 to 5 international outlets (Reuters, BBC, AP, Guardian or similar)
- **AI**: mix of outlets, company blogs, and Hacker News front page filtered for AI topics
- **Chile**: Emol and Cooperativa both publish reliable RSS, and Cooperativa breaks its feeds out by topic. La Tercera's RSS is less well documented, so verify it works before depending on it. BioBío as a fourth option.

Note that RSS feeds are reverse chronological. There is no "most read" or popularity signal available in them, and the most-read rankings that appear on the websites would require scraping. Do not build on those.

### 5.2 Ranking

**World and AI**: use cross-source agreement as the importance proxy. A story covered by most outlets in the pool is genuinely significant; one appearing in a single feed is filler. Cluster candidates by headline similarity, then rank clusters by source count and recency.

**Chile**: the source pool is too small for clustering to carry real signal, and Chilean outlets tend to either all agree or all diverge. Rank with the model directly instead, passing the full candidate list.

For all three categories, final selection runs through the model with three inputs:

1. The candidate headlines
2. The user preferences file (section 5.7)
3. The backlog of what was sent in the last 7 days (section 5.3)

Output per category: 3 items, each with a one or two sentence summary.

### 5.3 Backlog and repeat handling

For every item sent, store a fingerprint (normalised headline or URL), the date, and the one-line summary. Retain 7 days.

Running stories should not simply be suppressed, since a big story legitimately develops over several days. When a candidate matches a backlog entry, pass the previous summary to the model and ask it to either skip the item (genuinely nothing new) or reframe it as an update stating what changed. Prefer the update framing for developing stories.

### 5.4 Article fetch and embedding

Use `trafilatura` to extract clean article text, stripping navigation and ads. Embed the full text in the EPUB.

Fallback chain when extraction fails or the article is paywalled:

1. Use the RSS description or excerpt if it is substantial enough to stand alone
2. Otherwise include the summary plus an external link, and mark the item visibly as "full text unavailable"

Watch total file size. Amazon's send-to-Kindle email has a size limit, so very long articles should be truncated with a visible note rather than being allowed to break delivery.

### 5.5 Telegram inbox

Bot created via BotFather. The script polls the `getUpdates` endpoint on each run and drains pending messages. No webhook and no always-on process required, which keeps the whole thing laptop-local.

Message routing:

| Message shape | Action |
|---|---|
| Begins with "prefer" (case insensitive) | Append the remainder to the preferences file, reply with confirmation |
| Contains a URL | Add to the read-later queue with a timestamp |
| Plain text, no URL | Store as a standalone read-later item, no fetch needed |

That third case is the path for X posts. The post text cannot be pulled reliably: the official API's paid tier starts around $100/month, and unauthenticated scraping gets blocked quickly. The practical workaround is the phone share sheet, which usually carries the post text alongside the link, so the bot receives both in one tap. When an X post links out to a real article, send the underlying link instead of the X one.

### 5.6 Read-later queue

FIFO, capped at 5 items per edition, oldest first. The remainder rolls over to the next day. This prevents a Sunday link-dump from producing an unreadable Monday brick, while making sure nothing gets lost.

Read-later items are fetched and embedded exactly like news items, using the same fallback chain.

### 5.7 Preferences and exclusions

**Preferences file**: plain text, one instruction per line, for example "less football", "more Chilean economy", "more AI infrastructure, less product launches". Read on every run and pasted directly into the ranking prompt. Two write paths: edit the file on the laptop, or send a "prefer ..." message to the bot from the phone.

**Exclusions file**: a hard filter for categories that should never appear (gossip, sport, royals, and so on). Applied deterministically before ranking rather than left to the model's judgement.

### 5.8 EPUB structure

- Title page with the edition date
- Table of contents listing all nine headlines plus read-later items, each with its summary
- Each entry links down to the full text inside the same file
- Section order: World, AI, Chile, Read Later

### 5.9 Delivery

Email the EPUB to the Kindle address. The sending address must be added to the approved sender list in the Amazon account first. If it is not, delivery fails silently and everything else will appear to work correctly.

### 5.10 Failure handling

The script must produce and send an edition every day it runs. If sources fail, sections come back empty, or fetches break, the edition still goes out with a short status line at the top (for example, "3 of 5 world sources failed"). Silence is the one unacceptable outcome, because a missing delivery is indistinguishable from a slow news day and the whole thing quietly dies.

Log failures locally as well.

## 6. State files

| File | Purpose |
|---|---|
| `backlog.json` | Last 7 days of sent items with fingerprints and summaries |
| `queue.json` | Pending read-later items |
| `preferences.txt` | Steering instructions for the ranking prompt |
| `exclusions.txt` | Hard topic filters |
| `last_update_id` | Telegram polling offset |

## 7. Setup checklist

1. Create the bot with BotFather and save the token
2. Add the sending email address to the Amazon approved sender list
3. Find and verify every RSS feed URL, La Tercera especially
4. Build one edition manually and read it on the actual device before automating anything
5. Schedule the afternoon run

## 8. Open questions — resolved

- **AI feeds**: OpenAI, TechCrunch AI, The Verge AI, VentureBeat AI, plus HN frontpage filtered by keyword. Anthropic has no public RSS feed (verified) and isn't included, but AI-relevant Anthropic news still surfaces via the press outlets and HN when it's significant.
- **Language**: World and AI summaries in English, Chile in Spanish.
- **Images**: none, permanently — not just for v1.
- **Model / call structure**: one combined rank + summarize call per category. Runs against a local model via Ollama (default `llama3.1:8b`, configurable) rather than a cloud API — no key, nothing leaves the laptop, in keeping with the "no server, no hosting" non-goal read literally. Implemented in `src/rank.py`; live-tested on both the clustered path (World) and the flat-list path (Chile, Spanish output).

Also resolved during implementation, not originally flagged: **Emol's RSS has been discontinued** — every documented URL pattern now redirects to their plain HTML page. Dropped from the Chile source list; Cooperativa, BioBioChile, and La Tercera cover it (La Tercera's feed, flagged in the PRD as unverified, works fine at `/rss`).
