"""Deterministic cleanup, validation, and scoring."""

from __future__ import annotations

import re
from typing import Any

from src.validation.output_schema import brandattribute


_MODEL_FIELDS = getattr(brandattribute, "model_fields", None) or getattr(brandattribute, "__fields__", {})
OUTPUT_FIELDS = list(_MODEL_FIELDS.keys())


def post_process_extraction(record: dict[str, Any]) -> dict[str, str]:
    """Normalize extracted values and apply deterministic inference rules."""

    cleaned = {field: _clean_value(record.get(field, "")) for field in OUTPUT_FIELDS}
    cleaned["filename"] = _clean_value(record.get("filename", ""))
    cleaned["brand"] = _clean_value(record.get("brand", ""))

    for field in ["tb_test_required", "reauthorization_required", "step_through_phototherapy"]:
        cleaned[field] = _normalize_yes_no(cleaned[field])

    if (cleaned["reauthorization_duration"] or cleaned["reauthorization_requirements"]) and not cleaned["reauthorization_required"]:
        cleaned["reauthorization_required"] = "Yes"

    cleaned["number_of_steps_brands"] = _normalize_step_count(cleaned["number_of_steps_brands"])
    cleaned["number_of_steps_generic"] = _normalize_step_count(cleaned["number_of_steps_generic"])

    if cleaned["quantity_limits"] and re.search(r"\b(dosage|dosing limit|recommended dose)\b", cleaned["quantity_limits"], re.IGNORECASE):
        if not re.search(r"\bquantity limits?\b|\bQL\b", cleaned["quantity_limits"], re.IGNORECASE):
            cleaned["quantity_limits"] = ""

    if not cleaned["access_score"]:
        cleaned["access_score"] = compute_access_score(cleaned)

    return cleaned


def compute_access_score(record: dict[str, str]) -> str:
    """Compute a transparent coarse access score from extracted restrictions.

    This is intentionally simple and deterministic. If a payer-specific scoring
    rubric is later provided, it can replace this function without changing the
    extraction workflow.
    """

    restriction_points = 0
    for field in ["number_of_steps_brands", "number_of_steps_generic"]:
        value = record.get(field, "")
        if value.isdigit():
            restriction_points += int(value)
    if record.get("step_through_phototherapy") == "Yes":
        restriction_points += 1
    if record.get("reauthorization_required") == "Yes":
        restriction_points += 1
    if record.get("quantity_limits"):
        restriction_points += 1
    if restriction_points >= 5:
        return "Restrictive"
    if restriction_points >= 2:
        return "Moderate"
    return "Favorable"


def validate_output_record(record: dict[str, Any]) -> brandattribute:
    """Validate a final record with the required Pydantic schema."""

    return brandattribute(**record)


def load_output_schema() -> type[brandattribute]:
    """Return the schema class used for final row validation."""

    return brandattribute


def fallback_record(file_name: str, brand: str) -> dict[str, str]:
    """Create an empty schema-compatible row after a row-level failure."""

    return {field: "" for field in OUTPUT_FIELDS} | {"filename": file_name, "brand": brand}


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _normalize_yes_no(value: str) -> str:
    if not value:
        return ""
    lowered = value.lower()
    if lowered in {"y", "yes", "true"} or lowered.startswith("yes"):
        return "Yes"
    if lowered in {"n", "no", "false"} or lowered.startswith("no"):
        return "No"
    if lowered in {"na", "n/a", "not applicable"}:
        return "N/A"
    return value


def _normalize_step_count(value: str) -> str:
    if not value:
        return ""
    lowered = value.lower().strip()
    mapping = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "none": "NA", "n/a": "NA"}
    if lowered in mapping:
        return mapping[lowered]
    match = re.search(r"\b(\d+)\b", value)
    if match:
        return match.group(1)
    if lowered == "na":
        return "NA"
    return value
