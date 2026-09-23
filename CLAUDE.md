# kindle_news — read before touching this project

A daily Kindle news digest, local-only: RSS ingest, cross-source ranking, local-model
summarizing, EPUB delivery, and a Telegram bot for queueing reads (including X posts).

Full spec, stack, setup, and the running log of settled decisions live in `README.md` —
read it before making changes, not this file. `kindle-news-filter-prd.md` is the original
brief.

- `src/` — ingest, ranking, summarization, EPUB build
- `scripts/` — one-off / maintenance scripts
- `config/` — starter templates for `preferences.txt` / `exclusions.txt`
- `state/` — runtime data, gitignored, seeded from `config/` on first run
- `output/` — built editions, gitignored

## Repo

Git repo `sebagarciar/kindle-news-filter` on GitHub, **public**. Commit to `main`.

## Local only, no exceptions

No cloud AI API, no key, ever. Ranking and summarizing run through Ollama, model set by
`OLLAMA_MODEL` in `.env`. A first pass used the Anthropic API and was corrected to this —
don't reintroduce a cloud call for "better quality" without asking first.

## Not yet scheduled

Meant to run daily via cron/launchd, afternoon Madrid time — that's not wired up yet. It's
still started by hand with `python src/main.py`. Don't assume it runs automatically.

## JSON calls use `format: "json"`, not a schema

The ranking, topic-ban and Telegram calls ask Ollama for plain JSON and validate the
answer in code. Passing a full JSON schema instead was tested on 2026-09-23 with
llama3.1:8b and made both main calls worse: the ranking repeated a story in 2 of 3
runs, and forcing the ban topic to come from the ban list pushed the model's stray
flags past the validator, dropping an unrelated story in 3 of 3 runs. Re-test before
trying it again with a different model.
