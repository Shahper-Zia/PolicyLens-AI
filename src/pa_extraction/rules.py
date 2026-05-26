"""Load editable parameter rules for retrieval and extraction."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from src.pa_extraction.models import ParameterRule, RuleBook


FIELD_ALIASES: dict[str, str] = {
    "age": "age",
    "step therapy requirements documented in policy": "step_therapy_requirements",
    "number of steps through brands": "number_of_steps_brands",
    "number of steps through generic": "number_of_steps_generic",
    "step through-phototherapy": "step_through_phototherapy",
    "step through phototherapy": "step_through_phototherapy",
    "tb test required": "tb_test_required",
    "initial authorization duration(in-months)": "initial_auth_duration",
    "initial authorization duration": "initial_auth_duration",
    "reauthorization duration(in-months)": "reauthorization_duration",
    "reauthorization duration": "reauthorization_duration",
    "reauthorization required": "reauthorization_required",
    "reauthorization requirements documented in policy": "reauthorization_requirements",
    "specialist types": "specialist_types",
    "quantity limits": "quantity_limits",
    "access score": "access_score",
}

GROUPS: dict[str, list[str]] = {
    "eligibility": ["age", "specialist_types", "tb_test_required"],
    "step_therapy": [
        "step_therapy_requirements",
        "number_of_steps_brands",
        "number_of_steps_generic",
        "step_through_phototherapy",
    ],
    "authorization": [
        "initial_auth_duration",
        "reauthorization_duration",
        "reauthorization_required",
        "reauthorization_requirements",
    ],
    "limits": ["quantity_limits"],
    "scoring": ["access_score"],
}

DEFAULT_HINTS: dict[str, dict[str, list[str]]] = {
    "age": {
        "keywords": ["age", "adult", "pediatric", "years", "older", "younger", "FDA-approved"],
        "section_priorities": ["indication", "criteria", "description", "policy"],
        "inclusion_signals": ["patient", "adult", "years", "age", "FDA-Approved Indications"],
        "exclusion_signals": ["reference", "appendix", "history"],
    },
    "specialist_types": {
        "keywords": ["specialist", "prescriber", "prescribed by", "dermatologist", "rheumatologist", "gastroenterologist"],
        "section_priorities": ["criteria", "documentation", "policy"],
        "inclusion_signals": ["prescribed", "specialist", "consultation", "physician"],
        "exclusion_signals": ["reference"],
    },
    "tb_test_required": {
        "keywords": ["TB", "tuberculosis", "latent TB", "screening", "test"],
        "section_priorities": ["criteria", "documentation", "safety"],
        "inclusion_signals": ["TB", "tuberculosis", "screen", "test"],
        "exclusion_signals": ["not required", "reference"],
    },
    "step_therapy_requirements": {
        "keywords": ["step therapy", "preferred product", "trial", "failure", "inadequate response", "contraindication", "intolerance", "phototherapy"],
        "section_priorities": ["criteria", "all indications", "policy", "initial", "indication"],
        "inclusion_signals": ["trial", "failure", "preferred", "inadequate", "contraindication", "intolerance"],
        "exclusion_signals": ["references", "background", "dosing"],
    },
    "number_of_steps_brands": {
        "keywords": ["preferred product", "biologic", "adalimumab", "ustekinumab", "Enbrel", "Rinvoq", "Otezla", "brand"],
        "section_priorities": ["criteria", "all indications", "policy", "initial"],
        "inclusion_signals": ["preferred", "biologic", "product", "trial", "failure"],
        "exclusion_signals": ["phototherapy", "topical", "generic", "references"],
    },
    "number_of_steps_generic": {
        "keywords": ["topical", "conventional", "systemic", "methotrexate", "cyclosporine", "acitretin", "generic", "non-biologic"],
        "section_priorities": ["criteria", "all indications", "policy", "initial"],
        "inclusion_signals": ["trial", "failure", "topical", "systemic", "non-biologic"],
        "exclusion_signals": ["phototherapy", "references"],
    },
    "step_through_phototherapy": {
        "keywords": ["phototherapy", "PUVA", "UVA", "UVB", "light therapy"],
        "section_priorities": ["criteria", "description", "indication", "policy"],
        "inclusion_signals": ["phototherapy", "PUVA", "UVB", "required", "candidate"],
        "exclusion_signals": ["FDA-Approved Indications", "references"],
    },
    "initial_auth_duration": {
        "keywords": ["initial authorization", "initial approval", "approval duration", "duration", "months", "weeks"],
        "section_priorities": ["authorization", "duration", "approval", "criteria"],
        "inclusion_signals": ["initial", "authorization", "approval", "months"],
        "exclusion_signals": ["reauthorization", "continuation"],
    },
    "reauthorization_duration": {
        "keywords": ["reauthorization", "renewal", "continuation", "duration", "months"],
        "section_priorities": ["reauthorization", "continuation", "duration"],
        "inclusion_signals": ["reauthorization", "renewal", "continuation", "months"],
        "exclusion_signals": ["initial"],
    },
    "reauthorization_required": {
        "keywords": ["reauthorization", "renewal", "continuation", "continued approval"],
        "section_priorities": ["reauthorization", "continuation", "duration"],
        "inclusion_signals": ["reauthorization", "renewal", "continuation"],
        "exclusion_signals": [],
    },
    "reauthorization_requirements": {
        "keywords": ["continuation", "reauthorization", "renewal", "clinical benefit", "improvement", "response"],
        "section_priorities": ["reauthorization", "continuation", "documentation"],
        "inclusion_signals": ["improvement", "clinical benefit", "response", "continued"],
        "exclusion_signals": ["initial"],
    },
    "quantity_limits": {
        "keywords": ["quantity limit", "quantity limits", "QL", "maximum quantity"],
        "section_priorities": ["quantity", "limits", "policy"],
        "inclusion_signals": ["quantity limit", "quantity limits", "QL"],
        "exclusion_signals": ["dosage", "dosing limit", "recommended dose"],
    },
    "access_score": {
        "keywords": ["step therapy", "authorization", "quantity limit", "reauthorization"],
        "section_priorities": ["criteria", "authorization", "limits"],
        "inclusion_signals": [],
        "exclusion_signals": [],
    },
}


def load_rules(rules_path: str | Path) -> RuleBook:
    """Load parameter rules from JSON or the existing CSV-like markdown file.

    JSON is the most expressive format and supports aliases. The current
    `parameter_rules.md` is parsed as CSV so users can keep editing it in-place.
    """

    path = Path(rules_path)
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() == ".json":
        return _load_json_rules(json.loads(text))
    return _load_csv_markdown_rules(text)


def _load_json_rules(data: dict[str, Any]) -> RuleBook:
    parameters: dict[str, ParameterRule] = {}
    groups = data.get("groups") or GROUPS
    for item in data.get("parameters", []):
        output_field = _normalize_field(str(item.get("output_field") or item.get("name") or ""))
        if not output_field:
            continue
        group = str(item.get("group") or _group_for_field(output_field))
        defaults = DEFAULT_HINTS.get(output_field, {})
        parameters[output_field] = ParameterRule(
            name=str(item.get("name") or output_field),
            output_field=output_field,
            group=group,
            definition=str(item.get("definition") or ""),
            keywords=_dedupe([*defaults.get("keywords", []), *item.get("keywords", [])]),
            section_priorities=_dedupe([*defaults.get("section_priorities", []), *item.get("section_priorities", [])]),
            inclusion_signals=_dedupe([*defaults.get("inclusion_signals", []), *item.get("inclusion_signals", [])]),
            exclusion_signals=_dedupe([*defaults.get("exclusion_signals", []), *item.get("exclusion_signals", [])]),
            normalization_hints=list(item.get("normalization_hints", [])),
        )
    _ensure_default_rules(parameters)
    return RuleBook(
        parameters=parameters,
        groups={str(k): list(v) for k, v in groups.items()},
        brand_aliases={str(k).upper(): list(v) for k, v in (data.get("brand_aliases") or {}).items()},
        indication_aliases={str(k): list(v) for k, v in (data.get("indication_aliases") or {}).items()},
        raw=data,
    )


def _load_csv_markdown_rules(text: str) -> RuleBook:
    parameters: dict[str, ParameterRule] = {}
    reader = csv.reader(text.splitlines())
    rows = list(reader)
    for row in rows[1:]:
        if len(row) < 2:
            continue
        name, definition = row[0].strip(), row[1].strip()
        output_field = _normalize_field(name)
        if not output_field:
            continue
        defaults = DEFAULT_HINTS.get(output_field, {})
        parameters[output_field] = ParameterRule(
            name=name,
            output_field=output_field,
            group=_group_for_field(output_field),
            definition=definition,
            keywords=_dedupe([*defaults.get("keywords", []), *_keywords_from_definition(definition)]),
            section_priorities=defaults.get("section_priorities", []),
            inclusion_signals=defaults.get("inclusion_signals", []),
            exclusion_signals=defaults.get("exclusion_signals", []),
            normalization_hints=[],
        )
    _ensure_default_rules(parameters)
    return RuleBook(parameters=parameters, groups=GROUPS, raw={"source": "csv_markdown"})


def _ensure_default_rules(parameters: dict[str, ParameterRule]) -> None:
    for output_field, defaults in DEFAULT_HINTS.items():
        if output_field in parameters:
            continue
        parameters[output_field] = ParameterRule(
            name=output_field,
            output_field=output_field,
            group=_group_for_field(output_field),
            keywords=defaults.get("keywords", []),
            section_priorities=defaults.get("section_priorities", []),
            inclusion_signals=defaults.get("inclusion_signals", []),
            exclusion_signals=defaults.get("exclusion_signals", []),
        )


def _normalize_field(name: str) -> str:
    key = re.sub(r"\s+", " ", name.strip().lower())
    key = key.replace(" - ", "-").replace(" – ", "-")
    return FIELD_ALIASES.get(key, "")


def _group_for_field(field_name: str) -> str:
    for group, fields in GROUPS.items():
        if field_name in fields:
            return group
    return "other"


def _keywords_from_definition(definition: str) -> list[str]:
    phrases = re.findall(r'"([^"]+)"', definition)
    words = re.findall(r"\b[A-Za-z][A-Za-z-]{3,}\b", definition)
    stop = {"this", "that", "where", "which", "from", "with", "policy", "should", "required"}
    return _dedupe([*phrases, *[word for word in words if word.lower() not in stop]])[:30]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        cleaned = re.sub(r"\s+", " ", str(item)).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result
