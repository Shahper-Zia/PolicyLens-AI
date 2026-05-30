import math
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Sequence

from src.orchestrator.large_doc_extractor.chunker import LargeDocChunk
from src.orchestrator.lightweight_extractor.retriever import FIELD_QUERIES


IGNORED_SECTION_TERMS = (
    "references",
    "reference",
    "footnote",
    "footnotes",
    "appendix",
    "bibliography",
    "revision history",
    "policy history",
)

UNIVERSAL_TERMS = (
    "all indications",
    "for all indications",
    "all products",
    "all drugs",
    "all agents",
    "all biologics",
    "unless otherwise specified",
    "the indications below",
)

SECTION_TERMS = {
    "approval": ("approval criteria", "criteria", "must include", "patient meets", "required medical information"),
    "denial": ("denial criteria", "must not", "not receiving", "concurrent", "contraindicated"),
    "duration": ("duration of approval", "initial approval", "reauthorization approval", "coverage duration"),
    "reauthorization": ("reauthorization", "renewal", "continuation", "continued therapy"),
    "quantity": ("quantity limit", "quantity limits", "maximum quantity", "units per"),
    "safety": ("tuberculosis", "tb", "screening", "live vaccine", "infection", "hypersensitivity"),
}


def retrieve_large_doc_parameter_context(
    chunks: Sequence[LargeDocChunk],
    brand: str,
    field_name: str,
    vocabulary: Dict[str, Any],
    indication: str = "Psoriasis",
    max_chunks: int = 5,
    candidate_limit: int = 80,
) -> List[LargeDocChunk]:
    tagged_chunks = [tag_large_chunk(chunk, brand, vocabulary, indication) for chunk in chunks]
    tagged_chunks = [chunk for chunk in tagged_chunks if not _is_ignored_chunk(chunk)]

    candidate_pool = _candidate_pool(tagged_chunks, brand, vocabulary, indication, candidate_limit)
    universal_chunks = [chunk for chunk in candidate_pool if "universal" in chunk.tags][:2]
    field_ranked = _rank_for_field(candidate_pool, brand, field_name, vocabulary, indication)
    return _dedupe_chunks([*universal_chunks, *field_ranked])[:max_chunks]


def tag_large_chunk(
    chunk: LargeDocChunk,
    brand: str,
    vocabulary: Dict[str, Any],
    indication: str = "Psoriasis",
) -> LargeDocChunk:
    chunk.tags.clear()
    text = _normalize(f"{chunk.title}\n{chunk.text}")
    brand_aliases = _brand_aliases(brand, vocabulary)
    drug_terms = _terms(vocabulary, "drug_terms")
    indication_terms = [indication, *_terms(vocabulary, "indication_terms"), "psoriasis", "pso"]
    universal_terms = [*UNIVERSAL_TERMS, *_terms(vocabulary, "universal_markers")]

    if _contains_any(text, brand_aliases):
        chunk.tags.add("brand")
    if _contains_any(text, indication_terms):
        chunk.tags.add("indication")
    if _contains_any(text, universal_terms):
        chunk.tags.add("universal")
    if _contains_any(text, drug_terms):
        chunk.tags.add("drug_or_therapy")

    for tag, terms in SECTION_TERMS.items():
        if _contains_any(text, terms):
            chunk.tags.add(tag)

    return chunk


def _candidate_pool(
    chunks: Sequence[LargeDocChunk],
    brand: str,
    vocabulary: Dict[str, Any],
    indication: str,
    limit: int,
) -> List[LargeDocChunk]:
    scored = [(score_scope(chunk, brand, vocabulary, indication), chunk) for chunk in chunks]
    return [
        chunk
        for score, chunk in sorted(scored, key=lambda item: item[0], reverse=True)
        if score > 0
    ][:limit]


def score_scope(chunk: LargeDocChunk, brand: str, vocabulary: Dict[str, Any], indication: str) -> float:
    text = _normalize(f"{chunk.title}\n{chunk.text}")
    score = 0.0

    tag_weights = {
        "brand": 10,
        "indication": 8,
        "universal": 7,
        "approval": 4,
        "duration": 3,
        "reauthorization": 3,
        "quantity": 3,
        "safety": 2,
        "drug_or_therapy": 2,
    }
    for tag, weight in tag_weights.items():
        if tag in chunk.tags:
            score += weight

    for alias in _brand_aliases(brand, vocabulary):
        score += 2.0 * text.count(alias.lower())
    for term in _terms(vocabulary, "drug_terms"):
        score += 0.5 * text.count(term.lower())

    unrelated = ("crohn", "ulcerative colitis", "rheumatoid arthritis", "asthma")
    if "brand" not in chunk.tags and "universal" not in chunk.tags and _contains_any(text, unrelated):
        score -= 5

    return score


def score_field(chunk: LargeDocChunk, brand: str, field_name: str, vocabulary: Dict[str, Any], indication: str) -> float:
    text = _normalize(f"{chunk.title}\n{chunk.text}")
    token_counts = Counter(_tokens(text))
    score = score_scope(chunk, brand, vocabulary, indication) * 0.4

    for query in FIELD_QUERIES.get(field_name, ()):
        score += 10.0 * _cosine_token_overlap(token_counts, _tokens(query))

    if field_name == "age" and _contains_any(text, ("fda labeled age", "fda-labelled age", "fda approved age", "years of age")):
        score += 20
    if field_name in {"step_therapy_requirements", "number_of_steps_brands", "number_of_steps_generic", "step_through_phototherapy"}:
        if "approval" in chunk.tags:
            score += 8
        if "drug_or_therapy" in chunk.tags:
            score += 8
        if "phototherapy" in text and field_name == "step_through_phototherapy":
            score += 12
    if field_name == "initial_auth_duration" and _contains_any(text, ("duration of approval", "initial approval", "initial authorization")):
        score += 50
    if field_name in {"reauthorization_duration", "reauthorization_required", "reauthorization_requirements"}:
        if "reauthorization" in chunk.tags or "duration" in chunk.tags:
            score += 25
    if field_name == "tb_test_required" and _contains_any(text, ("tuberculosis", "tb", "screening", "test")):
        score += 20
    if field_name == "quantity_limits" and "quantity" in chunk.tags:
        score += 30
    if field_name == "specialist_types" and _contains_any(text, ("specialist", "dermatologist", "rheumatologist", "prescribed by", "consultation")):
        score += 20

    return score


def format_large_chunks_for_prompt(chunks: Iterable[LargeDocChunk], max_chars_per_chunk: int = 900) -> str:
    parts = []
    for chunk in chunks:
        tags = ", ".join(sorted(chunk.tags)) or "none"
        page = chunk.page_start if chunk.page_start is not None else "?"
        text = _trim_text(chunk.text, max_chars_per_chunk)
        parts.append(
            f"[{chunk.chunk_id} | page {page} | lines {chunk.start_line}-{chunk.end_line} | tags: {tags} | title: {chunk.title}]\n{text}"
        )
    return "\n\n---\n\n".join(parts)


def _rank_for_field(
    chunks: Sequence[LargeDocChunk],
    brand: str,
    field_name: str,
    vocabulary: Dict[str, Any],
    indication: str,
) -> List[LargeDocChunk]:
    scored = [(score_field(chunk, brand, field_name, vocabulary, indication), chunk) for chunk in chunks]
    return [
        chunk
        for score, chunk in sorted(scored, key=lambda item: item[0], reverse=True)
        if score > 1
    ]


def _brand_aliases(brand: str, vocabulary: Dict[str, Any]) -> List[str]:
    aliases = vocabulary.get("brand_aliases", {}).get(brand.upper(), [brand])
    return [alias.lower() for alias in aliases if isinstance(alias, str)]


def _terms(vocabulary: Dict[str, Any], key: str) -> List[str]:
    terms = vocabulary.get(key, [])
    return [term.lower() for term in terms if isinstance(term, str)]


def _is_ignored_chunk(chunk: LargeDocChunk) -> bool:
    title = _normalize(chunk.title)
    return _contains_any(title, IGNORED_SECTION_TERMS)


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term.lower() in text for term in terms)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _cosine_token_overlap(document_counts: Counter, query_tokens: List[str]) -> float:
    query_counts = Counter(query_tokens)
    if not document_counts or not query_counts:
        return 0.0

    dot = sum(document_counts[token] * query_counts[token] for token in query_counts)
    doc_norm = math.sqrt(sum(value * value for value in document_counts.values()))
    query_norm = math.sqrt(sum(value * value for value in query_counts.values()))
    return dot / (doc_norm * query_norm)


def _dedupe_chunks(chunks: Sequence[LargeDocChunk]) -> List[LargeDocChunk]:
    seen = set()
    deduped = []
    for chunk in chunks:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        deduped.append(chunk)
    return deduped


def _trim_text(text: str, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rsplit(" ", 1)[0] + " ..."
