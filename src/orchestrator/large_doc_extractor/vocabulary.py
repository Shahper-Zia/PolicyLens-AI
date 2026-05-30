import json
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Sequence

from src.orchestrator.large_doc_extractor.chunker import LargeDocChunk
from src.orchestrator.lightweight_extractor.groq_client import GroqClient


KNOWN_BRAND_ALIASES = {
    "TREMFYA": ["TREMFYA", "guselkumab"],
    "STELARA": ["STELARA", "ustekinumab"],
}

THERAPY_PATTERN = re.compile(
    r"\b("
    r"adalimumab|ustekinumab|guselkumab|methotrexate|cyclosporine|acitretin|apremilast|"
    r"leflunomide|sulfasalazine|etanercept|infliximab|ixekizumab|secukinumab|"
    r"risankizumab|tildrakizumab|phototherapy|puva|uvb|tnf blocker|tnf inhibitor|"
    r"topical agent|topical therapy|biologic|biosimilar|targeted synthetic|"
    r"conventional systemic|systemic therapy|non-biologic"
    r")\b",
    re.IGNORECASE,
)

INDICATION_PATTERN = re.compile(
    r"\b(pso|psoriasis|plaque psoriasis|moderate[- ]to[- ]severe psoriasis|"
    r"moderate[- ]to[- ]severe plaque psoriasis)\b",
    re.IGNORECASE,
)


def build_large_doc_vocabulary(
    chunks: Sequence[LargeDocChunk],
    brand_names: Sequence[str],
    indication: str,
    groq_client: GroqClient,
    use_llm: bool = True,
) -> Dict[str, Any]:
    candidates = scan_vocabulary_candidates(chunks, brand_names)
    if not use_llm:
        return candidates

    prompt = _build_vocabulary_prompt(chunks, brand_names, indication, candidates)
    messages = [
        {
            "role": "system",
            "content": "You clean retrieval vocabulary from payer policy text. Return valid JSON only.",
        },
        {
            "role": "user",
            "content": prompt,
        },
    ]
    response_text = groq_client.chat(messages, temperature=0.0)
    payload = _parse_json_object(response_text)
    return normalize_vocabulary(payload or candidates, brand_names, candidates)


def scan_vocabulary_candidates(chunks: Sequence[LargeDocChunk], brand_names: Sequence[str]) -> Dict[str, Any]:
    brand_aliases = {brand.upper(): set(KNOWN_BRAND_ALIASES.get(brand.upper(), [brand])) for brand in brand_names}
    drug_terms = set()
    indication_terms = set()
    universal_markers = set()

    for chunk in chunks:
        text = _compact_text(f"{chunk.title}\n{chunk.text}")
        text_lower = text.lower()

        for brand in brand_names:
            if brand.lower() in text_lower:
                brand_aliases.setdefault(brand.upper(), set()).add(brand)
            for alias in KNOWN_BRAND_ALIASES.get(brand.upper(), []):
                if alias.lower() in text_lower:
                    brand_aliases.setdefault(brand.upper(), set()).add(alias)

        drug_terms.update(match.group(0) for match in THERAPY_PATTERN.finditer(text))
        indication_terms.update(match.group(0) for match in INDICATION_PATTERN.finditer(text))

        for marker in ("all indications", "for all indications", "all products", "all biologics", "unless otherwise specified"):
            if marker in text_lower:
                universal_markers.add(marker)

    return {
        "brand_aliases": {brand: sorted(values) for brand, values in brand_aliases.items()},
        "drug_terms": _top_terms(drug_terms),
        "indication_terms": _top_terms(indication_terms),
        "universal_markers": sorted(universal_markers),
    }


def normalize_vocabulary(payload: Dict[str, Any], brand_names: Sequence[str], fallback: Dict[str, Any]) -> Dict[str, Any]:
    brand_aliases = payload.get("brand_aliases", {})
    if not isinstance(brand_aliases, dict):
        brand_aliases = {}

    normalized_aliases = {}
    for brand in brand_names:
        values = brand_aliases.get(brand) or brand_aliases.get(brand.upper()) or fallback["brand_aliases"].get(brand.upper(), [])
        if isinstance(values, str):
            values = [values]
        normalized_aliases[brand.upper()] = _clean_terms([brand, *values])

    return {
        "brand_aliases": normalized_aliases,
        "drug_terms": _clean_terms(payload.get("drug_terms", fallback.get("drug_terms", []))),
        "indication_terms": _clean_terms(payload.get("indication_terms", fallback.get("indication_terms", []))),
        "universal_markers": _clean_terms(payload.get("universal_markers", fallback.get("universal_markers", []))),
    }


def _build_vocabulary_prompt(
    chunks: Sequence[LargeDocChunk],
    brand_names: Sequence[str],
    indication: str,
    candidates: Dict[str, Any],
) -> str:
    preview = _candidate_preview(chunks, brand_names)
    return f"""
Target brands: {", ".join(brand_names)}
Target indication: {indication} / PsO / Psoriasis

Candidate vocabulary found by deterministic scanning:
{json.dumps(candidates, indent=2)}

Clean and expand only from the supplied text preview. Do not invent external drug mappings.

Return exactly one JSON object:
{{
  "brand_aliases": {{"<BRAND>": ["aliases/generic names explicitly present"]}},
  "drug_terms": ["therapy/drug terms explicitly present"],
  "indication_terms": ["indication terms explicitly present"],
  "universal_markers": ["phrases showing all-indication/all-product criteria"]
}}

Text preview:
{preview}
""".strip()


def _candidate_preview(chunks: Sequence[LargeDocChunk], brand_names: Sequence[str], max_chars: int = 7500) -> str:
    needles = [brand.lower() for brand in brand_names]
    needles.extend(["psoriasis", "pso", "all indications", "criteria", "authorization", "quantity limit"])
    selected = []
    total = 0

    for chunk in chunks:
        text = _compact_text(f"{chunk.title}\n{chunk.text}")
        if not any(needle in text.lower() for needle in needles):
            continue
        part = f"[{chunk.chunk_id} | page {chunk.page_start} | lines {chunk.start_line}-{chunk.end_line} | {chunk.title}]\n{text}"
        if total + len(part) > max_chars:
            break
        selected.append(part)
        total += len(part)

    return "\n\n---\n\n".join(selected)


def _top_terms(terms: Iterable[str], limit: int = 80) -> List[str]:
    counts = Counter(term.strip() for term in terms if term and term.strip())
    return [term for term, _ in counts.most_common(limit)]


def _clean_terms(terms: Any) -> List[str]:
    if not isinstance(terms, list):
        return []
    cleaned = []
    seen = set()
    for term in terms:
        if not isinstance(term, str):
            continue
        compact = _compact_text(term)
        if not compact:
            continue
        key = compact.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(compact)
    return cleaned


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _parse_json_object(response_text: str) -> Dict[str, Any]:
    response_text = response_text.strip()
    try:
        parsed = json.loads(response_text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, character in enumerate(response_text):
            if character != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(response_text[index:])
            except json.JSONDecodeError:
                continue
            return parsed if isinstance(parsed, dict) else {}
    return {}
