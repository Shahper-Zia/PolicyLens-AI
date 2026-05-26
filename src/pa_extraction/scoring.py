"""Deterministic chunk scoring and row-specific scoping helpers."""

from __future__ import annotations

import re
from dataclasses import replace

from src.pa_extraction.models import Chunk, ExtractionContext, ParameterRule, RuleBook


UNRELATED_SCOPE_TERMS = [
    "references",
    "bibliography",
]


def build_extraction_context(
    file_name: str,
    brand: str,
    indication: str,
    rules: RuleBook,
) -> ExtractionContext:
    """Construct normalized brand and indication terms from external aliases."""

    brand_clean = _clean_term(brand)
    indication_clean = _clean_term(indication)
    brand_terms = _dedupe([brand_clean, *rules.brand_aliases.get(brand_clean.upper(), [])])
    indication_terms = _dedupe([indication_clean, *rules.indication_aliases.get(indication_clean, [])])
    return ExtractionContext(
        file_name=file_name.strip(),
        brand=brand_clean,
        indication=indication_clean,
        brand_terms=brand_terms,
        indication_terms=indication_terms,
    )


def get_relevant_chunks_for_parameter_group(
    chunks: list[Chunk],
    group_name: str,
    rules: RuleBook,
    context: ExtractionContext,
    top_k_per_parameter: int = 6,
    max_group_chunks: int = 14,
) -> list[Chunk]:
    """Retrieve high-signal chunks for all parameters in a logical group."""

    selected: dict[int, Chunk] = {}
    fields = rules.groups.get(group_name, [])
    for field in fields:
        rule = rules.parameters.get(field)
        if not rule:
            continue
        scored = [
            score_chunks_for_parameter(chunk, rule, context)
            for chunk in chunks
        ]
        scored = [
            chunk
            for chunk in scored
            if chunk.score > 3
            and "other_indication_section" not in chunk.reasons
            and "reference_like" not in chunk.reasons
        ]
        scored.sort(key=lambda chunk: chunk.score, reverse=True)
        for chunk in scored[:top_k_per_parameter]:
            existing = selected.get(chunk.chunk_index)
            if existing is None or chunk.score > existing.score:
                selected[chunk.chunk_index] = chunk

    ranked = sorted(selected.values(), key=lambda chunk: chunk.score, reverse=True)
    return ranked[:max_group_chunks]


def score_chunks_for_parameter(chunk: Chunk, rule: ParameterRule, context: ExtractionContext) -> Chunk:
    """Score a chunk for one parameter while enforcing row-specific scope."""

    text = chunk.text
    lowered = text.lower()
    section_lowered = f"{chunk.section_title} {chunk.section_type}".lower()
    score = 0.0
    reasons: list[str] = []

    brand_hits = _term_hits(text, context.brand_terms)
    indication_hits = _term_hits(text, context.indication_terms)
    keyword_hits = _term_hits(text, rule.keywords)
    inclusion_hits = _term_hits(text, rule.inclusion_signals)
    exclusion_hits = _term_hits(text, rule.exclusion_signals)
    section_hits = [signal for signal in rule.section_priorities if signal.lower() in section_lowered]

    if brand_hits:
        score += 8 + min(len(brand_hits), 3)
        reasons.append(f"brand:{','.join(brand_hits[:3])}")
    if indication_hits:
        score += 9 + min(len(indication_hits), 3)
        reasons.append(f"indication:{','.join(indication_hits[:3])}")
    if keyword_hits:
        score += 2 * min(len(keyword_hits), 8)
        reasons.append(f"keywords:{','.join(keyword_hits[:5])}")
    if inclusion_hits:
        score += 2 * min(len(inclusion_hits), 5)
        reasons.append(f"inclusion:{','.join(inclusion_hits[:4])}")
    if section_hits:
        score += 3 * min(len(section_hits), 3)
        reasons.append(f"section:{','.join(section_hits[:3])}")
    if _has_proximity(text, [*context.brand_terms, *context.indication_terms], rule.keywords):
        score += 6
        reasons.append("proximity")

    if chunk.section_type in {"reference"} or "reference" in section_lowered or any(term in lowered for term in UNRELATED_SCOPE_TERMS):
        score -= 20
        reasons.append("scope_penalty")
    if _looks_like_reference_chunk(text):
        score -= 25
        reasons.append("reference_like")
    if _looks_like_other_indication_section(chunk.section_title, context.indication_terms):
        score -= 12
        reasons.append("other_indication_section")
    if exclusion_hits:
        score -= 3 * min(len(exclusion_hits), 4)
        reasons.append(f"exclusion:{','.join(exclusion_hits[:4])}")

    # Generic all-indication criteria can matter, but unrelated indication-only
    # chunks should not outrank chunks naming the target scope.
    if not brand_hits and not indication_hits:
        if chunk.section_type in {"all_indications", "criteria", "authorization", "quantity"} and keyword_hits:
            score += 2
            reasons.append("universal_policy_candidate")
        else:
            score -= 8
            reasons.append("missing_target_scope")

    return replace(chunk, score=round(score, 3), reasons=tuple(reasons))


def _term_hits(text: str, terms: list[str]) -> list[str]:
    hits: list[str] = []
    for term in terms:
        if not term:
            continue
        pattern = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            hits.append(term)
    return _dedupe(hits)


def _has_proximity(text: str, scope_terms: list[str], keywords: list[str], window: int = 450) -> bool:
    lowered = text.lower()
    scope_positions = [lowered.find(term.lower()) for term in scope_terms if term and lowered.find(term.lower()) >= 0]
    keyword_positions = [lowered.find(term.lower()) for term in keywords if term and lowered.find(term.lower()) >= 0]
    return any(abs(scope_pos - keyword_pos) <= window for scope_pos in scope_positions for keyword_pos in keyword_positions)


def _looks_like_other_indication_section(section_title: str, target_terms: list[str]) -> bool:
    lowered = section_title.lower()
    if any(re.search(r"(?<![A-Za-z0-9])" + re.escape(term.lower()) + r"(?![A-Za-z0-9])", lowered) for term in target_terms if term):
        return False
    # Many policy headings carry disease acronyms in parentheses. If a heading
    # has such an acronym but none of the target indication terms, keep it from
    # competing with the target-specific criteria.
    return bool(re.search(r"\([A-Za-z]{2,6}\)", section_title))


def _looks_like_reference_chunk(text: str) -> bool:
    citation_years = len(re.findall(r"\b(?:19|20)\d{2};\d", text))
    numbered_citations = len(re.findall(r"(?:^|\n)\s*\d+\.\s+[A-Z][A-Za-z-]+", text))
    journal_terms = len(re.findall(r"\b(?:Dermatol|Rheumatol|Gastroenterol|Arthritis|Lancet|Medicine|Journal)\b", text))
    return citation_years >= 2 or numbered_citations >= 2 or journal_terms >= 4


def _clean_term(value: str) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
