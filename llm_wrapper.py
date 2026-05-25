"""Lightweight LLM router for brand extraction.

Default provider: Gemini
Optional provider: llama via local Ollama endpoint.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any, Dict, List


def _load_env_file() -> None:
    if os.getenv("GEMINI_API_KEY"):
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


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _call_gemini(prompt: str) -> str:
    _load_env_file()

    try:
        from google import genai
    except ImportError as exc:
        raise ImportError(
            "google-genai is not installed. Install it or use LLM_PROVIDER=llama."
        ) from exc

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    model_name = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
    )
    return getattr(response, "text", "") or str(response)


def _call_llama(prompt: str) -> str:
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


def call_llm(prompt: str, provider: str | None = None) -> str:
    provider = (provider or os.getenv("LLM_PROVIDER", "gemini")).lower().strip()
    if provider == "llama":
        return _call_llama(prompt)
    return _call_gemini(prompt)


def extract_brands_from_markdown(file_name: str, markdown_text: str, provider: str | None = None) -> Dict[str, List[str]]:
    from src.prompts.brand_extraction_prompt import build_brand_extraction_prompt

    prompt = build_brand_extraction_prompt(file_name, markdown_text)
    raw_response = call_llm(prompt, provider=provider)
    parsed = _extract_json(raw_response)

    brands = parsed.get("brands", [])
    if not isinstance(brands, list):
        brands = []

    cleaned = []
    seen = set()
    for brand in brands:
        if not isinstance(brand, str):
            continue
        normalized = re.sub(r"\s+", " ", brand).strip()
        if not normalized:
            continue
        key = normalized.upper()
        if key not in seen:
            seen.add(key)
            cleaned.append(key)

    return {file_name: cleaned}
