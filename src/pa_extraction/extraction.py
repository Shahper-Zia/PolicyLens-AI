"""LLM-backed and deterministic grouped field extraction."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.pa_extraction.models import Chunk, ExtractionContext, RuleBook
from src.pa_extraction.prompts import build_group_extraction_prompt

LOGGER = logging.getLogger(__name__)


def extract_group_fields(
    group_name: str,
    chunks: list[Chunk],
    rules: RuleBook,
    context: ExtractionContext,
    provider: str | None = None,
    use_llm: bool = True,
) -> dict[str, str]:
    """Extract one logical group, with heuristic fallback for resilience."""

    fields = rules.groups.get(group_name, [])
    if not fields:
        return {}
    result = {field: "" for field in fields}
    if not chunks:
        return result

    if use_llm:
        try:
            prompt = build_group_extraction_prompt(group_name, fields, rules.parameters, chunks, context)
            from src.llm.router import call_llm

            raw_response = call_llm(prompt, provider=provider)
            parsed = _extract_json_object(raw_response)
            for field in fields:
                value = parsed.get(field, "")
                result[field] = _stringify(value)
            return result
        except Exception as exc:  # noqa: BLE001 - pipeline should continue row-by-row.
            LOGGER.warning("LLM extraction failed for %s/%s/%s: %s", context.file_name, context.brand, group_name, exc)

    heuristic = _heuristic_extract_group(group_name, chunks)
    result.update({field: heuristic.get(field, "") for field in fields})
    return result


def _heuristic_extract_group(group_name: str, chunks: list[Chunk]) -> dict[str, str]:
    text = "\n\n".join(chunk.text for chunk in chunks)
    result: dict[str, str] = {}

    if group_name == "eligibility":
        result["age"] = _first_sentence_matching(text, [r"\badult patients?\b", r"\b\d+\s*years?\b", r"\bage\b"])
        result["specialist_types"] = _first_sentence_matching(
            text,
            [r"dermatologist", r"rheumatologist", r"gastroenterologist", r"\bspecialist\b"],
        )
        result["tb_test_required"] = "Yes" if re.search(r"\b(TB|tuberculosis)\b", text, re.IGNORECASE) else ""
    elif group_name == "step_therapy":
        step_text = _sentences_matching(
            text,
            [r"preferred product", r"step therapy", r"\btrial\b", r"inadequate response", r"contraindication", r"intolerance"],
            limit=8,
        )
        result["step_therapy_requirements"] = step_text
        result["step_through_phototherapy"] = _phototherapy_status(text)
        result["number_of_steps_brands"] = _count_branded_steps(text)
        result["number_of_steps_generic"] = _count_generic_steps(text)
    elif group_name == "authorization":
        result["initial_auth_duration"] = _duration_near(text, ["initial", "authorization", "approval"])
        result["reauthorization_duration"] = _duration_near(text, ["reauthorization", "renewal", "continuation"])
        result["reauthorization_requirements"] = _sentences_matching(
            text,
            [r"reauthorization", r"continuation", r"clinical benefit", r"improvement", r"response"],
            limit=5,
        )
        if result["reauthorization_duration"] or result["reauthorization_requirements"]:
            result["reauthorization_required"] = "Yes"
    elif group_name == "limits":
        result["quantity_limits"] = _sentences_matching(text, [r"quantity limits?", r"\bQL\b", r"maximum quantity"], limit=4)
    elif group_name == "scoring":
        result["access_score"] = ""

    return result


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("LLM response was not a JSON object.")
    return parsed


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    if isinstance(value, (list, tuple)):
        return "; ".join(_stringify(item) for item in value if _stringify(item))
    return str(value).strip()


def _first_sentence_matching(text: str, patterns: list[str]) -> str:
    sentences = _sentences_matching(text, patterns, limit=1)
    return sentences


def _sentences_matching(text: str, patterns: list[str], limit: int = 5) -> str:
    pieces = re.split(r"(?<=[.!?])\s+|\n{2,}", text)
    matches: list[str] = []
    for piece in pieces:
        cleaned = re.sub(r"\s+", " ", piece).strip(" -\t\r\n")
        if not cleaned:
            continue
        if any(re.search(pattern, cleaned, re.IGNORECASE) for pattern in patterns):
            if cleaned not in matches:
                matches.append(cleaned)
        if len(matches) >= limit:
            break
    return "; ".join(matches)


def _duration_near(text: str, anchors: list[str]) -> str:
    duration_pattern = r"(\b\d+\s*(?:months?|weeks?|days?)\b|\bunspecified\b)"
    for match in re.finditer(duration_pattern, text, flags=re.IGNORECASE):
        window = text[max(0, match.start() - 250): match.end() + 250]
        if any(anchor.lower() in window.lower() for anchor in anchors):
            return match.group(1)
    return ""


def _phototherapy_status(text: str) -> str:
    if not re.search(r"\b(phototherapy|PUVA|UVB|UVA)\b", text, flags=re.IGNORECASE):
        return ""
    if re.search(r"\b(candidate for|fda-approved indications?)\b", text, flags=re.IGNORECASE):
        return "No"
    if re.search(r"\b(required|trial|failure|inadequate|step)\b", text, flags=re.IGNORECASE):
        return "Yes"
    return ""


def _count_branded_steps(text: str) -> str:
    if not re.search(r"\b(preferred product|biologic|adalimumab|ustekinumab|Enbrel|Rinvoq|Otezla)\b", text, re.IGNORECASE):
        return ""
    explicit = re.search(r"\b(ONE|TWO|THREE|FOUR|FIVE|\d+)\s+(?:additional\s+)?preferred products?\b", text, re.IGNORECASE)
    if explicit:
        return _word_number_to_digit(explicit.group(1))
    return ""


def _count_generic_steps(text: str) -> str:
    if re.search(r"\b(topical|methotrexate|cyclosporine|acitretin|non-biologic|conventional systemic)\b", text, re.IGNORECASE):
        return "1"
    return ""


def _word_number_to_digit(value: str) -> str:
    mapping = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5"}
    return mapping.get(value.lower(), value)
