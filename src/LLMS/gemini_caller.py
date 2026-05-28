"""Gemini client settings and helpers."""

from __future__ import annotations

import json
import os
import re
import time
from threading import Lock
from typing import Any, Dict, List

GEMINI_DEFAULT_MODEL = "gemini-3.1-flash-lite"
_RATE_LOCK = Lock()
_LAST_CALL_TS = 0.0


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


def _respect_rpm_limit() -> None:
    global _LAST_CALL_TS
    rpm = int(os.getenv("GEMINI_RPM_LIMIT", "15"))
    if rpm <= 0:
        return
    min_interval = 60.0 / float(rpm)
    with _RATE_LOCK:
        now = time.time()
        elapsed = now - _LAST_CALL_TS
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _LAST_CALL_TS = time.time()


def call_gemini(prompt: str, *, model_name: str | None = None, max_retries: int | None = None) -> str:
    try:
        from google import genai
    except ImportError as exc:
        raise ImportError(
            "google-genai is not installed. Add it to requirements.txt."
        ) from exc

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    model_name = model_name or os.getenv("GEMINI_MODEL", GEMINI_DEFAULT_MODEL)
    max_retries = max_retries or int(os.getenv("GEMINI_MAX_RETRIES", "4"))
    sleep_base = float(os.getenv("GEMINI_RETRY_SLEEP_BASE", "2"))

    client = genai.Client(api_key=api_key)

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            _respect_rpm_limit()
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            return getattr(response, "text", "") or str(response)
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            time.sleep(sleep_base * attempt)

    raise RuntimeError(f"Gemini call failed after {max_retries} attempts: {last_error}")


def parse_brand_response(raw_text: str) -> List[str]:
    parsed = _extract_json(raw_text)
    brands = parsed.get("brands", [])
    if not isinstance(brands, list):
        return []

    cleaned: List[str] = []
    seen = set()
    for brand in brands:
        if not isinstance(brand, str):
            continue
        normalized = re.sub(r"\s+", " ", brand).strip().upper()
        if not normalized:
            continue
        if normalized not in seen:
            seen.add(normalized)
            cleaned.append(normalized)
    return cleaned


generate = call_gemini
