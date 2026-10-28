"""Model client, shared by rank.py (select+summarize headlines), youtube.py
(summarize video transcripts), preferences.py and telegram_bot.py.

Two backends. Ollama is local: no API key, nothing leaves the laptop. Claude
runs the `claude -p` command-line tool on Seba's own login (no API key).
LLM_BACKEND in .env picks which one handles the heavy calls (the ranking and
summarizing in rank.py, which pass heavy=True). Every other call stays on
Ollama.

Ollama's own default context window is small (a few thousand tokens) and it
truncates a longer prompt silently rather than erroring, so anything that
feeds the model a lot of text — a video transcript, above all — has to pass
its own num_ctx in options. A silently clipped prompt looks exactly like a
model that ignored half the material.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import requests

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:latest")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "sonnet")
# The scheduled task may start with a short PATH, so fall back to the usual install spot.
CLAUDE_BIN = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
REQUEST_TIMEOUT = 180  # local inference on a laptop CPU/GPU can be slow


def generate(
    prompt: str,
    json_mode: bool = False,
    options: dict | None = None,
    timeout: int = REQUEST_TIMEOUT,
    heavy: bool = False,
) -> str:
    """One-shot call to the model. Raises on any failure.

    heavy=True sends the call to Claude when LLM_BACKEND=claude. Otherwise it
    goes to the local Ollama model.

    options passes Ollama generation parameters straight through (num_ctx,
    temperature, num_predict); timeout is per call, since a long-context
    summarization takes several times what a headline ranking call does.
    """
    if heavy and os.environ.get("LLM_BACKEND", "ollama") == "claude":
        return _generate_claude(prompt, timeout)
    # think=False: reasoning models (qwen3.5) otherwise spend the whole budget thinking
    # and return an empty "response".
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "think": False}
    if json_mode:
        payload["format"] = "json"
    if options:
        payload["options"] = options
    response = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()["response"]


def _generate_claude(prompt: str, timeout: int) -> str:
    """One call to Claude through the `claude -p` command-line tool.

    Runs from an empty temp folder with no tools, no saved session and no
    settings, so it never loads this project's CLAUDE.md or touches a file.
    Uses the login from `claude /login`. Raises if the tool fails.
    """
    with tempfile.TemporaryDirectory() as workdir:
        result = subprocess.run(
            [
                CLAUDE_BIN, "-p",
                "--model", CLAUDE_MODEL,
                "--output-format", "text",
                "--tools", "",
                "--no-session-persistence",
                "--disable-slash-commands",
                "--setting-sources", "",
            ],
            input=prompt, capture_output=True, text=True,
            timeout=timeout, cwd=workdir,
        )
    if result.returncode != 0:
        raise RuntimeError(f"claude -p failed: {(result.stderr or result.stdout).strip()[:300]}")
    return _strip_json_fence(result.stdout)


def _strip_json_fence(text: str) -> str:
    """Claude sometimes wraps JSON in a ```json fence. Ollama never does."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()
