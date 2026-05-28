from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any
import json
from src.config.logging import logger
from src.LLMS import llm_wrapper

from src.orchestrator.chunker.Documents_chunked import (
    Chunk,
    Section,
    build_contextual_chunks,
    parse_document_into_sections,
)


def get_brand_indication_chunks(
    source: Any,
    brands: list[str],
    indication: str | None = None,
    *,
    brand_aliases: list[str] | None = None,
    indication_aliases: list[str] | None = None,
    max_chars: int = 2200,
    min_chunk_score: float = 6.0,
    weak_chunk_score: float = -3.0,
    use_llm_scoring: bool = False,
    llm_candidate_limit: int = 12,
    min_llm_score: float = 6.0,
) -> dict[str, dict[str, Any]]:
    """
    Chunk a policy document and keep chunks that look relevant to a brand and
    indication.

    If no indication is provided, defaults to Psoriasis.

    The selection logic is intentionally two-stage:
    1. score each chunk using scope terms in the body and the section title
    2. keep weak chunks only when they immediately follow a strong chunk
    """

    indication = indication or "Psoriasis"
    document_text, source_name = _coerce_text_source(source)
    sections = parse_document_into_sections(document_text)
    chunks = build_contextual_chunks(sections, max_chars=max_chars)

    relevant_chunks_by_brand: dict[str, dict[str, Any]] = {}

    for brand in brands:
        brand_terms = _expand_terms(brand, brand_aliases or [])
        indication_terms = _expand_terms(indication, indication_aliases or [])

        section_infos = _score_sections(sections, chunks, brand_terms, indication_terms)
        scored_chunks = [
            _score_chunk(
                chunk,
                brand_terms=brand_terms,
                indication_terms=indication_terms,
            )
            for chunk in chunks
        ]
        if use_llm_scoring:
            scored_chunks = _llm_score_candidate_chunks(
                scored_chunks,
                brand=brand,
                indication=indication,
                candidate_limit=llm_candidate_limit,
                min_llm_score=min_llm_score,
            )
        scored_chunks = _apply_neighbor_score_boost(
            scored_chunks,
            strong_score=min_chunk_score,
            boosted_score=4.5,
        )
        final_chunks = _select_neighbor_chunks(
            scored_chunks,
            min_chunk_score=min_chunk_score,
            weak_chunk_score=weak_chunk_score,
        )
        logger.info(
            f"{brand} final chunk selection complete: selected_chunks={len(final_chunks)}, "
            f"selected_sections={len({chunk['section_title'] for chunk in final_chunks})}"
        )
        logger.info(
            f"Chunking document: source={source_name}, document_length={len(document_text)}, "
            f"sections={len(sections)}, chunks={len(chunks)}, use_llm_scoring={use_llm_scoring}"
        )
        relevant_chunks_by_brand[brand] = {
            "source_name": source_name,
            "brand": brand,
            "indication": indication,
            "document_length": len(document_text),
            "selected_sections": sorted({chunk["section_title"] for chunk in final_chunks}),
            "section_scores": section_infos,
            "chunks": final_chunks,
        }

    return relevant_chunks_by_brand

def _apply_neighbor_score_boost(
    scored_chunks: list[dict[str, Any]],
    *,
    strong_score: float,
    boosted_score: float,
) -> list[dict[str, Any]]:
    ordered = sorted(scored_chunks, key=lambda item: item["chunk_index"])

    for index, chunk in enumerate(ordered):
        current_score = float(chunk.get("final_score", chunk["score"]))

        if current_score >= strong_score:
            continue

        previous_chunk = ordered[index - 1] if index > 0 else None
        next_chunk = ordered[index + 1] if index + 1 < len(ordered) else None

        previous_is_strong = (
            previous_chunk is not None
            and previous_chunk.get("section_title") == chunk.get("section_title")
            and float(previous_chunk.get("final_score", previous_chunk["score"])) >= strong_score
        )

        next_is_strong = (
            next_chunk is not None
            and next_chunk.get("section_title") == chunk.get("section_title")
            and float(next_chunk.get("final_score", next_chunk["score"])) >= strong_score
        )

        if previous_is_strong or next_is_strong:
            chunk["final_score"] = max(current_score, boosted_score)
            chunk["reasons"].append("neighbor_score_boost")

    return ordered

def _coerce_text_source(source: Any) -> tuple[str, str | None]:
    source_name = None
    raw_document: Any = source

    if hasattr(source, "read"):
        raw_document = source.read()
        source_name = getattr(source, "filename", None) or getattr(source, "name", None)
    elif isinstance(source, (str, Path)):
        candidate = Path(str(source))
        if isinstance(source, Path) or (candidate.exists() and "\n" not in str(source)):
            raw_document = candidate.read_text(encoding="utf-8", errors="ignore")
            source_name = candidate.name

    if isinstance(raw_document, bytes):
        document_text = raw_document.decode("utf-8", errors="ignore")
    else:
        document_text = str(raw_document)

    return document_text, source_name


def _score_sections(
    sections: list[Section],
    chunks: list[Chunk],
    brand_terms: list[str],
    indication_terms: list[str],
) -> list[dict[str, Any]]:
    chunks_by_section: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        chunks_by_section[chunk.section_title].append(chunk)

    results: list[dict[str, Any]] = []

    for section in sections:
        title_text = section.title
        body_text = section.text
        combined = f"{title_text}\n{body_text}"

        title_brand_hits = _term_hits(title_text, brand_terms)
        title_indication_hits = _term_hits(title_text, indication_terms)
        body_brand_hits = _term_hits(body_text, brand_terms)
        body_indication_hits = _term_hits(body_text, indication_terms)

        score = 0.0
        reasons: list[str] = []

        if title_brand_hits:
            score += 7 + min(len(title_brand_hits), 3)
            reasons.append(f"title_brand:{','.join(title_brand_hits[:3])}")
        if title_indication_hits:
            score += 8 + min(len(title_indication_hits), 3)
            reasons.append(f"title_indication:{','.join(title_indication_hits[:3])}")
        if body_brand_hits:
            score += 4 + min(len(body_brand_hits), 3)
            reasons.append(f"body_brand:{','.join(body_brand_hits[:3])}")
        if body_indication_hits:
            score += 5 + min(len(body_indication_hits), 3)
            reasons.append(f"body_indication:{','.join(body_indication_hits[:3])}")

        if title_brand_hits and title_indication_hits:
            score += 8
            reasons.append("title_scope_exact")
        elif body_brand_hits and body_indication_hits:
            score += 5
            reasons.append("body_scope_exact")
        elif title_indication_hits:
            score += 3
            reasons.append("title_indication_anchor")
        elif title_brand_hits:
            score += 2
            reasons.append("title_brand_anchor")

        if _has_proximity(combined, brand_terms, indication_terms, window=350):
            score += 4
            reasons.append("brand_indication_proximity")

        if _looks_like_reference(section.title, body_text):
            score -= 20
            reasons.append("reference_like")

        if not title_brand_hits and not title_indication_hits and not body_brand_hits and not body_indication_hits:
            score -= 4
            reasons.append("missing_scope_terms")

        results.append(
            {
                "section_title": section.title,
                "section_type": section.section_type,
                "score": round(score, 3),
                "reasons": reasons,
                "chunk_count": len(chunks_by_section.get(section.title, [])),
            }
        )

    return results

def _llm_score_candidate_chunks(
    scored_chunks: list[dict[str, Any]],
    *,
    brand: str,
    indication: str,
    candidate_limit: int,
    min_llm_score: float,
) -> list[dict[str, Any]]:
    candidates = sorted(
        [
            chunk for chunk in scored_chunks
            if _is_llm_candidate(chunk)
        ],
        key=lambda chunk: chunk["score"],
        reverse=True,
    )[:candidate_limit]
    logger.info(
    f"LLM scoring candidates selected: brand={brand}, indication={indication}, "
    f"candidate_count={len(candidates)}, candidate_limit={candidate_limit}"
    )
    candidate_indexes = {chunk["chunk_index"] for chunk in candidates}

    for chunk in scored_chunks:
        chunk["llm_score"] = None
        chunk["llm_relevant"] = None
        chunk["llm_reason"] = None
        chunk["final_score"] = chunk["score"]

        if chunk["chunk_index"] not in candidate_indexes:
            continue

        try:
            logger.info(
                f"Calling LLM for chunk: brand={brand}, idx={chunk.get('chunk_index')}, "
                f"rule_score={chunk.get('score')}, section={chunk.get('section_title')}"
            )
            llm_result = _call_llm_for_chunk(
                chunk=chunk,
                brand=brand,
                indication=indication,
            )

            llm_score = float(llm_result.get("score", 0))
            llm_relevant = bool(llm_result.get("relevant", False))
            llm_reason = str(llm_result.get("reason", ""))

            chunk["llm_score"] = llm_score
            chunk["llm_relevant"] = llm_relevant
            chunk["llm_reason"] = llm_reason

            if llm_relevant and llm_score >= min_llm_score:
                chunk["final_score"] = max(chunk["score"], llm_score)
                chunk["reasons"].append("llm_relevant")
            else:
                chunk["final_score"] = min(chunk["score"], llm_score)
                chunk["reasons"].append("llm_not_relevant")
                logger.info(
                f"LLM scored chunk: brand={brand}, idx={chunk.get('chunk_index')}, "
                f"rule_score={chunk.get('score')}, llm_score={llm_score}, "
                f"llm_relevant={llm_relevant}, final_score={chunk.get('final_score')}, "
                f"llm_reason={llm_reason}"
            )
        except Exception as exc:
            logger.warning(
                f"LLM scoring failed for chunk {chunk.get('chunk_index')}: {exc}"
            )
            chunk["reasons"].append("llm_scoring_failed")

    return scored_chunks


def _is_llm_candidate(chunk: dict[str, Any]) -> bool:
    score = float(chunk.get("score", 0))
    reasons = chunk.get("reasons", [])

    if "reference_like" in reasons:
        return False

    if score >= -3:
        return True

    return bool(
        reason.startswith("brand:")
        or reason.startswith("indication:")
        or reason in {"section_brand", "section_indication"}
        for reason in reasons
    )

def _call_llm_for_chunk(
    *,
    chunk: dict[str, Any],
    brand: str,
    indication: str,
) -> dict[str, Any]:
    prompt = _build_llm_scoring_prompt(
        chunk=chunk,
        brand=brand,
        indication=indication,
    )

    response = llm_wrapper.generate(prompt)

    return _parse_llm_score_response(response)

def _build_llm_scoring_prompt(
    *,
    chunk: dict[str, Any],
    brand: str,
    indication: str,
) -> str:
    return f"""
You are scoring whether a payer policy document chunk is relevant to a target brand and indication.

Target brand: {brand}
Target indication: {indication}

Section title:
{chunk.get("section_title", "")}

Chunk text:
{chunk.get("text", "")}

Return only valid JSON with this shape:
{{
"relevant": true or false,
"score": number from 0 to 10,
"reason": "short explanation"
}}

Scoring guidance:
- 0 means completely irrelevant.
- 5 means possibly related but weak.
- 8-10 means clearly relevant to the brand and indication.
- Do not mark a chunk relevant only because it mentions the indication generally.
- Prefer chunks that contain coverage criteria, authorization rules, step therapy, quantity limits, reauthorization, or policy requirements for the target brand/indication.Even if the chunk contains the generic name of the brand the chunk score should be high only if the content is clearly about the target brand, not just mentioning the drug class or indication. For example, a chunk that mentions "tumor necrosis factor inhibitors" and "psoriasis" without mentioning the brand name may be relevant to the indication but not specifically relevant to the brand, so it should receive a moderate score. On the other hand, a chunk that mentions "Humira" or its generic name and "psoriasis" and describes specific coverage criteria for Humira would be highly relevant and should receive a high score.DO NOT HALLUCINATE GENERIC NAMES OF THE BRAND. If the brand name is not mentioned in the chunk, do not ASSUME a generic name and do not give the chunk a high score based on the indication alone. Focus on the specific content of the chunk and its relevance to the target brand and indication.
""".strip()


def _parse_llm_score_response(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response

    text = str(response).strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()

    parsed = json.loads(text)

    return {
        "relevant": bool(parsed.get("relevant", False)),
        "score": float(parsed.get("score", 0)),
        "reason": str(parsed.get("reason", "")),
    }

def _select_neighbor_chunks(
    scored_chunks: list[dict[str, Any]],
    *,
    min_chunk_score: float,
    weak_chunk_score: float,
) -> list[dict[str, Any]]:
    ordered = sorted(scored_chunks, key=lambda item: item["chunk_index"])
    selected: list[dict[str, Any]] = []
    previous_was_strong = False

    for chunk in ordered:
        score = float(chunk.get("final_score", chunk["score"]))
        is_strong = score >= min_chunk_score
        is_weak = weak_chunk_score <= score < min_chunk_score

        if is_strong:
            chunk["selection_reason"] = "strong"
            selected.append(chunk)
            previous_was_strong = True
            continue

        if is_weak and previous_was_strong:
            chunk["selection_reason"] = "neighbor_of_strong"
            selected.append(chunk)
            previous_was_strong = False
            continue

        previous_was_strong = False

    return selected


def _score_chunk(
    chunk: Chunk,
    *,
    brand_terms: list[str],
    indication_terms: list[str],
) -> dict[str, Any]:
    text = chunk.text
    title = chunk.section_title

    brand_hits = _term_hits(text, brand_terms)
    indication_hits = _term_hits(text, indication_terms)
    title_brand_hits = _term_hits(title, brand_terms)
    title_indication_hits = _term_hits(title, indication_terms)

    score = 0.0
    reasons: list[str] = []

    if brand_hits:
        score += 6 + min(len(brand_hits), 3)
        reasons.append(f"brand:{','.join(brand_hits[:3])}")
    if indication_hits:
        score += 7 + min(len(indication_hits), 3)
        reasons.append(f"indication:{','.join(indication_hits[:3])}")
    if title_brand_hits:
        score += 3
        reasons.append("section_brand")
    if title_indication_hits:
        score += 4
        reasons.append("section_indication")
    if brand_hits and indication_hits:
        score += 6
        reasons.append("exact_scope_chunk")
    if _has_proximity(text, brand_terms, indication_terms, window=300):
        score += 3
        reasons.append("brand_indication_proximity")
    if _looks_like_reference(title, text):
        score -= 20
        reasons.append("reference_like")
    if not brand_hits and not indication_hits and not title_brand_hits and not title_indication_hits:
        score -= 3
        reasons.append("missing_scope_terms")

    return {
        "chunk_index": chunk.chunk_index,
        "section_title": chunk.section_title,
        "section_type": chunk.section_type,
        "heading_level": chunk.heading_level,
        "start": chunk.start,
        "end": chunk.end,
        "score": round(score, 3),
        "reasons": reasons,
        "text": chunk.text,
    }


def _expand_terms(primary: str, aliases: list[str]) -> list[str]:
    raw_terms = [primary, *aliases]
    expanded: list[str] = []

    for term in raw_terms:
        cleaned = _normalize_term(term)
        if not cleaned:
            continue
        expanded.append(cleaned)

        without_parens = re.sub(r"\s*\([^)]*\)\s*", " ", cleaned).strip()
        if without_parens and without_parens.lower() != cleaned.lower():
            expanded.append(without_parens)

        collapsed = re.sub(r"[-_/]+", " ", cleaned).strip()
        if collapsed and collapsed.lower() != cleaned.lower():
            expanded.append(collapsed)

    return _dedupe(expanded)


def _term_hits(text: str, terms: list[str]) -> list[str]:
    hits: list[str] = []
    for term in terms:
        if not term:
            continue
        pattern = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            hits.append(term)
    return _dedupe(hits)


def _has_proximity(text: str, left_terms: list[str], right_terms: list[str], window: int = 300) -> bool:
    lowered = text.lower()
    left_positions = [lowered.find(term.lower()) for term in left_terms if term and lowered.find(term.lower()) >= 0]
    right_positions = [lowered.find(term.lower()) for term in right_terms if term and lowered.find(term.lower()) >= 0]
    return any(abs(a - b) <= window for a in left_positions for b in right_positions)


def _looks_like_reference(title: str, text: str) -> bool:
    lowered_title = title.lower()
    if any(term in lowered_title for term in ["reference", "bibliography", "appendix"]):
        return True

    citation_years = len(re.findall(r"\b(?:19|20)\d{2};\d", text))
    numbered_citations = len(re.findall(r"(?:^|\n)\s*\d+\.\s+[A-Z][A-Za-z-]+", text))
    journal_terms = len(re.findall(r"\b(?:Dermatol|Rheumatol|Gastroenterol|Arthritis|Lancet|Medicine|Journal)\b", text))
    return citation_years >= 2 or numbered_citations >= 2 or journal_terms >= 4


def _normalize_term(value: str) -> str:
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
