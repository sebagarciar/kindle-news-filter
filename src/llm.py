"""Local Ollama client, shared by rank.py (select+summarize headlines) and
youtube.py (summarize video transcripts). No API key, nothing leaves the
laptop.

Ollama's own default context window is small (a few thousand tokens) and it
truncates a longer prompt silently rather than erroring, so anything that
feeds the model a lot of text — a video transcript, above all — has to pass
its own num_ctx in options. A silently clipped prompt looks exactly like a
model that ignored half the material.
"""

from __future__ import annotations

import os

import requests

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
REQUEST_TIMEOUT = 180  # local inference on a laptop CPU/GPU can be slow


def generate(
    prompt: str,
    json_mode: bool = False,
    options: dict | None = None,
    timeout: int = REQUEST_TIMEOUT,
) -> str:
    """One-shot call to the local model. Raises on any HTTP/connection failure.

    options passes Ollama generation parameters straight through (num_ctx,
    temperature, num_predict); timeout is per call, since a long-context
    summarization takes several times what a headline ranking call does.
    """
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    if json_mode:
        payload["format"] = "json"
    if options:
        payload["options"] = options
    response = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()["response"]
