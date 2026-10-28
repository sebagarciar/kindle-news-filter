# kindle_news: read before touching this project

A daily Kindle news digest, local-only: RSS ingest, cross-source ranking, local-model
summarizing, EPUB delivery, and a Telegram bot for queueing reads (including X posts).

Full spec, stack, setup, and the running log of settled decisions live in `README.md` , 
read it before making changes, not this file. `kindle-news-filter-prd.md` is the original
brief.

- `src/`: ingest, ranking, summarization, EPUB build
- `scripts/`: one-off / maintenance scripts
- `config/`: starter templates for `preferences.txt` / `exclusions.txt`
- `state/`: runtime data, gitignored, seeded from `config/` on first run
- `output/`: built editions, gitignored

## Repo

Git repo `sebagarciar/kindle-news-filter` on GitHub, **public**. Commit to `main`.

## Models: Claude for the heavy calls, Ollama for the rest

No cloud AI API and no API key, ever. Changed by Seba on 2026-10-28: the ranking,
summaries, Background boxes, analysis matching and storylines (`heavy=True` in
`src/llm.py`) run through the `claude -p` tool on his own Claude login when
`LLM_BACKEND=claude` is set in `.env`. Model: `CLAUDE_MODEL`, default `sonnet`.
Everything else (Telegram sorting, topic bans, YouTube notes) stays on local
Ollama, model set by `OLLAMA_MODEL` in `.env` (now qwen3.5; Llama 3.1 8B is
uninstalled). `LLM_BACKEND=ollama` puts all of it back on Ollama. The login can
expire: if runs fail with an authentication error, run `claude /login`.
Don't add a call that needs an API key without asking first.

## Daily schedule: Claude desktop scheduled task

Decided by Seba, 2026-10-28. The task `kindle-news-daily` (Claude app, Scheduled section)
runs `scripts/run_daily.sh` at 12, 14, 16, 17, 18 and 20:00 local time. The script exits
at once if today's edition is already in `state/run.log`, so it sends once a day. It also
starts Ollama if it is down and uses a lock so runs never overlap. The Mac must be awake
and the Claude app open; a missed slot runs when the app next opens. The script
itself calls `claude -p` for the heavy model calls (see above). The task lives in the
Claude app (Scheduled section) and in `~/.claude/scheduled-tasks/kindle-news-daily/SKILL.md`,
not in this repo. Nothing is in launchd or cron; the plist in `scripts/` is the unused
alternative.

## JSON calls use `format: "json"`, not a schema

The ranking, topic-ban and Telegram calls ask Ollama for plain JSON and validate the
answer in code. Passing a full JSON schema instead was tested on 2026-09-23 with
llama3.1:8b and made both main calls worse: the ranking repeated a story in 2 of 3
runs, and forcing the ban topic to come from the ban list pushed the model's stray
flags past the validator, dropping an unrelated story in 3 of 3 runs. That test was on Llama, which is
no longer installed. The code now runs on qwen3.5 (thinking turned off in `llm.py`),
so the result is untested on it. Re-test before changing it.
