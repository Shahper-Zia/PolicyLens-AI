"""Groq-backed Llama client settings and helpers."""

from __future__ import annotations

import json
import os
import re
import time
from threading import Lock
from typing import Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI

from src.config.logging import logger

load_dotenv()

LLAMA_DEFAULT_MODEL = "llama-3.3-70b-versatile"
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
    rpm = int(os.getenv("LLAMA_RPM_LIMIT", "15"))
    if rpm <= 0:
        return
    min_interval = 60.0 / float(rpm)
    with _RATE_LOCK:
        now = time.time()
        elapsed = now - _LAST_CALL_TS
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _LAST_CALL_TS = time.time()


def call_llama(prompt: str, *, max_retries: int | None = None, max_output_tokens: int | None = None) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set.")

    model_name = os.getenv("LLAMA_MODEL", os.getenv("GROQ_MODEL", LLAMA_DEFAULT_MODEL))
    max_retries = max_retries or int(os.getenv("LLAMA_MAX_RETRIES", "4"))
    sleep_base = float(os.getenv("LLAMA_RETRY_SLEEP_BASE", "2"))
    max_output_tokens = max_output_tokens or int(os.getenv("LLAMA_MAX_NEW_TOKENS", "128"))

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            _respect_rpm_limit()
            response = client.responses.create(
                model=model_name,
                input=prompt,
                temperature=0,
                max_output_tokens=max_output_tokens,
            )
            logger.info("Received Llama response")
            return response.output_text
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            time.sleep(sleep_base * attempt)

    raise RuntimeError(f"Llama call failed after {max_retries} attempts: {last_error}")


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


generate = call_llama
