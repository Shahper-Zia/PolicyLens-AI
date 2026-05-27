from __future__ import annotations

import json
import re
from typing import Any

from src.LLMS import llm_wrapper
from src.config.logging import logger


_GENERIC_NAME_CACHE: dict[str, str] = {}


def extract_parameter(
    brand_section: str,
    rule_content: str,
    *,
    brand: str | None = None,
    indication: str | None = None,
) -> str:
    """
    Extract one access parameter from selected PA policy chunks using the rule
    document provided for that parameter.
    """

    parameter_name = _extract_parameter_name(rule_content)
    target_brand = _clean_optional(brand)
    target_indication = _clean_optional(indication)
    generic_name = _resolve_generic_name(target_brand) if target_brand else "NA"

    prompt = _build_extraction_prompt(
        brand_section=brand_section,
        rule_content=rule_content,
        parameter_name=parameter_name,
        brand=target_brand or "Not provided",
        generic_name=generic_name,
        indication=target_indication or "Not provided",
    )

    logger.info(
        "Extracting parameter with LLM: parameter=%s, brand=%s, indication=%s, chunk_chars=%s",
        parameter_name,
        target_brand or "Not provided",
        target_indication or "Not provided",
        len(brand_section),
    )

    try:
        response = llm_wrapper.generate(prompt)
        parsed = _parse_json_response(response)
        value = _normalize_value(parsed.get("value"))

        if not value:
            return "NA"

        logger.info(
            "Extracted parameter: parameter=%s, value=%s, confidence=%s",
            parameter_name,
            value,
            parsed.get("confidence", "NA"),
        )
        return value
    except Exception as exc:
        logger.warning("Parameter extraction failed for %s: %s", parameter_name, exc)
        return "NA"


def _resolve_generic_name(brand: str) -> str:
    cache_key = brand.lower()
    if cache_key in _GENERIC_NAME_CACHE:
        return _GENERIC_NAME_CACHE[cache_key]

    prompt = f"""
Return the generic or nonproprietary name for this drug brand.

Brand: {brand}

Rules:
- Return only valid JSON.
- If you are not certain, return "NA".
- Do not guess or invent a generic name.

JSON shape:
{{
  "generic_name": "string"
}}
""".strip()

    try:
        response = llm_wrapper.generate(prompt)
        parsed = _parse_json_response(response)
        generic_name = _normalize_value(parsed.get("generic_name")) or "NA"
        _GENERIC_NAME_CACHE[cache_key] = generic_name
        return generic_name
    except Exception as exc:
        logger.warning("Generic name lookup failed for brand %s: %s", brand, exc)
        _GENERIC_NAME_CACHE[cache_key] = "NA"
        return "NA"


def _build_extraction_prompt(
    *,
    brand_section: str,
    rule_content: str,
    parameter_name: str,
    brand: str,
    generic_name: str,
    indication: str,
) -> str:
    return f"""
You are extracting one structured access parameter from prior authorization policy chunks.

Business context:
We are a pharma company evaluating how easily patients can access our brand through insurance coverage. Extract only what is supported by the policy text for the target brand and indication. Do not hallucinate.

Target brand: {brand}
Target generic/nonproprietary name: {generic_name}
Target indication: {indication}
Parameter to extract: {parameter_name}

Parameter rule document:
{rule_content}

Selected policy chunks:
{brand_section}

Extraction requirements:
- Use the parameter rule document as the source of extraction logic.
- Use only the selected policy chunks as evidence.
- Prefer evidence specific to the target brand and target indication.
- If the chunks include other brands or other indications, do not use those as evidence for the target brand.
- If the rule requires an explicit statement and the chunks do not contain it, return "NA".
- If evidence conflicts, prefer the most specific text for the target brand and target indication.
- Preserve the policy meaning but keep the value concise.
- Do not include explanations in the value field.

Return only valid JSON with this exact shape:
{{
  "parameter": "{parameter_name}",
  "value": "extracted value or NA",
  "evidence": "short quote or summary of supporting policy text",
  "confidence": "high, medium, or low"
}}
""".strip()


def _extract_parameter_name(rule_content: str) -> str:
    for line in rule_content.splitlines():
        heading_match = re.match(r"^\s*#\s+(.+?)\s*$", line)
        if heading_match:
            return heading_match.group(1).strip()
    return "Unknown Parameter"


def _parse_json_response(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response

    text = str(response).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _normalize_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    return cleaned


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    return cleaned or None
