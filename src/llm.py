"""Local Ollama client, shared by rank.py (select+summarize headlines) and
youtube.py (summarize video transcripts). No API key, nothing leaves the
laptop.
"""

from __future__ import annotations

import os

import requests

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
REQUEST_TIMEOUT = 180  # local inference on a laptop CPU/GPU can be slow


def generate(prompt: str, json_mode: bool = False) -> str:
    """One-shot call to the local model. Raises on any HTTP/connection failure."""
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    if json_mode:
        payload["format"] = "json"
    response = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()["response"]
