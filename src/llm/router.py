"""Provider router for brand extraction LLM calls."""

from __future__ import annotations

import os
from typing import List

from src.llm.gemini_client import call_gemini, parse_brand_response


def call_llm(prompt: str, provider: str | None = None) -> str:
    provider = (provider or os.getenv("LLM_PROVIDER", "gemini")).lower().strip()
    if provider == "gemini":
        return call_gemini(prompt)
    raise ValueError(f"Unsupported LLM provider: {provider}")


def extract_brands_from_llm_output(raw_text: str) -> List[str]:
    return parse_brand_response(raw_text)
