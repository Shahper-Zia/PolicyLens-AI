"""Narrow prompts for grouped PA extraction."""

from __future__ import annotations

import json

from src.pa_extraction.models import Chunk, ExtractionContext, ParameterRule


def build_group_extraction_prompt(
    group_name: str,
    fields: list[str],
    rules: dict[str, ParameterRule],
    chunks: list[Chunk],
    context: ExtractionContext,
) -> str:
    """Build a tightly scoped JSON-only prompt for one field group."""

    field_contract = {
        field: {
            "definition": rules[field].definition,
            "keywords": rules[field].keywords,
            "normalization_hints": rules[field].normalization_hints,
        }
        for field in fields
        if field in rules
    }
    chunk_payload = [
        {
            "chunk_index": chunk.chunk_index,
            "section_title": chunk.section_title,
            "section_type": chunk.section_type,
            "score": chunk.score,
            "reasons": list(chunk.reasons),
            "text": chunk.text,
        }
        for chunk in chunks
    ]
    empty_contract = {field: "" for field in fields}
    return f"""You extract structured prior authorization policy parameters.

Target scope:
- file_name: {context.file_name}
- brand: {context.brand}
- indication: {context.indication}
- brand aliases: {context.brand_terms}
- indication aliases: {context.indication_terms}

Critical scoping rules:
- Extract only values grounded in the target file, target brand, and target indication.
- Do not extract values from unrelated indications, unrelated products, references, exclusions, or examples.
- A chunk that merely mentions the target indication as a prerequisite for another indication is not target-scope evidence.
- Universal/all-indications criteria may be used only when they apply to the target brand/indication and do not conflict with indication-specific criteria.
- Phototherapy language may appear inside step therapy text, but never count phototherapy as a branded or generic step.
- If the evidence is not explicit or not scoped, return an empty string for that field.

Group: {group_name}
Return JSON only with exactly these keys:
{json.dumps(empty_contract, indent=2)}

Field rules:
{json.dumps(field_contract, indent=2)}

Retrieved evidence chunks:
{json.dumps(chunk_payload, indent=2)}
"""
