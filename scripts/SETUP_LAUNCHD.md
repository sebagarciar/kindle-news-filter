# Scheduling the daily run (launchd)

This has to be installed once, on this Mac, in a real Terminal — it can't
be done from a cloud/remote session, since launchd and Ollama both live on
this machine, not in the cloud.

1. Copy the job definition into place:

   ```bash
   cp /Users/seba/Documents/ia_os/kindle_news/scripts/com.seba.kindlenews.plist \
      ~/Library/LaunchAgents/
   ```

2. Load it:

   ```bash
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.seba.kindlenews.plist
   ```

   (On older macOS without `bootstrap`, use `launchctl load ~/Library/LaunchAgents/com.seba.kindlenews.plist` instead.)

3. It's set to run daily at 17:00 (afternoon, per the PRD). To change the
   time, edit the `Hour`/`Minute` values in the plist, then re-run step 2
   (or `launchctl bootout gui/$(id -u)/com.seba.kindlenews` first if it's
   already loaded).

4. Test it immediately without waiting for 17:00:

   ```bash
   launchctl kickstart gui/$(id -u)/com.seba.kindlenews
   ```

   Check `state/launchd.log` for the script's stdout/stderr, and
   `state/run.log` for the pipeline's own log.

## Requirements at run time

- Ollama must be running (the menu-bar app, or `ollama serve`) with the
  configured model pulled — the job does not start it.
- The Mac needs to be awake (not asleep) at the scheduled time. `pmset
  repeat` or an equivalent wake schedule can help if it's usually asleep
  in the afternoon.

## Why this isn't run from a Claude Cowork schedule instead

A Cowork scheduled task in the cloud can reach files in this connected
folder, but its shell is a separate sandboxed environment with no network
access and no path to this Mac's installed Python or its local Ollama
service — the pipeline can't actually execute there. Running it as a
launchd job on this machine, where Ollama and the venv already live, is
the reliable way to get a daily edition.
