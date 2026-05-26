"""Provider router for LLM calls.

Supports Gemini, Groq-hosted Llama models, and an optional local Ollama endpoint.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import List

from src.llm.gemini_client import call_gemini, parse_brand_response


def _load_env_file() -> None:
    """Load local `.env` values into the process environment if needed."""

    if os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("OLLAMA_URL"):
        return

    env_path = ".env"
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value


def call_ollama(prompt: str) -> str:
    """Call a local Ollama-compatible endpoint."""

    base_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    model_name = os.getenv("LLAMA_MODEL", "llama3.1")
    payload = json.dumps(
        {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data.get("response", "")


def call_groq(prompt: str) -> str:
    """Call Groq through its OpenAI-compatible chat completions endpoint."""

    api_url = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1").rstrip("/")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set.")

    model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    max_tokens = int(os.getenv("MAX_OUTPUT_TOKENS", "8192"))
    payload = json.dumps(
        {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "Return only the requested JSON or plain text output. Do not add commentary."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": max_tokens,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        f"{api_url}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        data = json.loads(response.read().decode("utf-8"))
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return message.get("content", "") or ""


def call_llm(prompt: str, provider: str | None = None) -> str:
    _load_env_file()
    provider = (provider or os.getenv("LLM_PROVIDER", "gemini")).lower().strip()
    if provider == "gemini":
        return call_gemini(prompt)
    if provider in {"groq", "llama"}:
        return call_groq(prompt)
    if provider in {"ollama", "local"}:
        return call_ollama(prompt)
    raise ValueError(f"Unsupported LLM provider: {provider}")


def extract_brands_from_llm_output(raw_text: str) -> List[str]:
    return parse_brand_response(raw_text)
