import math
import re
from collections import Counter
from typing import Dict, Iterable, List, Mapping, Sequence

from src.orchestrator.lightweight_extractor.chunker import PolicyChunk
from src.orchestrator.lightweight_extractor.rules import FIELD_TO_RULE_FILE


BRAND_ALIASES: Dict[str, Sequence[str]] = {
    "TREMFYA": ("tremfya", "guselkumab"),
    "STELARA": ("stelara", "ustekinumab"),
}

INDICATION_ALIASES: Sequence[str] = (
    "pso",
    "psoriasis",
    "plaque psoriasis",
    "moderate-to-severe psoriasis",
    "moderate to severe psoriasis",
    "moderate-to-severe plaque psoriasis",
    "moderate to severe plaque psoriasis",
)

UNIVERSAL_TERMS: Sequence[str] = (
    "all indications",
    "for all indications",
    "all fda-approved indications",
    "all fda approved indications",
    "all fda-labelled indications",
    "all fda labeled indications",
    "all products",
    "all drugs",
    "all agents",
    "all biologics",
    "all medications",
    "all covered uses",
    "all non-preferred",
    "all nonpreferred",
    "unless otherwise specified",
    "applies to all",
    "the indications below",
)

IGNORED_SECTION_TERMS: Sequence[str] = (
    "references",
    "reference",
    "footnote",
    "footnotes",
    "appendix",
    "bibliography",
    "revision history",
    "policy history",
)

APPROVAL_TERMS: Sequence[str] = (
    "approval criteria",
    "initial authorization request",
    "must include",
    "patient meets",
    "required medical information",
)

DENIAL_TERMS: Sequence[str] = (
    "denial criteria",
    "will be denied",
    "not medically necessary",
    "must not",
    "should not",
    "not receiving",
    "concurrent therapy",
    "concurrent phototherapy",
    "contraindicated",
)

DURATION_TERMS: Sequence[str] = (
    "duration of approval",
    "initial approval",
    "reauthorization approval",
    "coverage duration",
    "authorization period",
)

SAFETY_TERMS: Sequence[str] = (
    "cautions",
    "warnings",
    "tuberculosis",
    "tb",
    "live vaccines",
    "hypersensitivity",
    "infection",
)

DRUG_AND_THERAPY_TERMS: Sequence[str] = (
    "adalimumab",
    "apremilast",
    "acitretin",
    "cyclosporine",
    "methotrexate",
    "leflunomide",
    "sulfasalazine",
    "ustekinumab",
    "guselkumab",
    "ixekizumab",
    "secukinumab",
    "risankizumab",
    "tildrakizumab",
    "etanercept",
    "infliximab",
    "tnf blocker",
    "tnf inhibitor",
    "topical agent",
    "topical corticosteroid",
    "conventional systemic",
    "conventional synthetic",
    "systemic therapy",
    "non-biologic",
    "biologic",
    "biosimilar",
    "targeted synthetic",
    "phototherapy",
    "puva",
    "uvb",
)

PARAMETER_TERMS: Sequence[str] = (
    "age",
    "years of age",
    "adult",
    "step therapy",
    "trial and failure",
    "inadequate response",
    "contraindication",
    "intolerance",
    "preferred",
    "non-preferred",
    "nonpreferred",
    "phototherapy",
    "puva",
    "tuberculosis",
    "tb",
    "screening",
    "quantity limit",
    "ql",
    "prescriber",
    "specialist",
    "dermatologist",
    "authorization",
    "approval duration",
    "coverage duration",
    "initial authorization",
    "reauthorization",
    "renewal",
    "continuation",
    "continued therapy",
    *DRUG_AND_THERAPY_TERMS,
)

PARAMETER_QUERIES: Sequence[str] = (
    "age eligibility age restriction adults years of age",
    "step therapy prior therapy preferred product non-preferred biologic trial failure contraindication intolerance",
    "phototherapy puva light therapy required before approval",
    "tuberculosis tb test screening igra tst required",
    "quantity limit ql units per days per month",
    "specialist prescriber dermatologist rheumatologist consultation",
    "initial authorization approval duration coverage duration months",
    "reauthorization renewal continuation continued therapy duration clinical response",
)

FIELD_QUERIES: Dict[str, Sequence[str]] = {
    "age": (
        "age eligibility restriction limit adults pediatric years old years of age",
        "minimum age maximum age patient must be adult member age",
    ),
    "step_therapy_requirements": (
        "step therapy prior therapy trial failure inadequate response intolerance contraindication required medical information",
        "preferred non-preferred biologic product must try fail before approval alternative therapy",
    ),
    "number_of_steps_brands": (
        "branded biologic biosimilar targeted synthetic named drug preferred adalimumab ustekinumab guselkumab step",
        "non-preferred agent must use preferred biologic product prior to requested medication",
    ),
    "number_of_steps_generic": (
        "generic non-biologic conventional systemic topical methotrexate cyclosporine acitretin apremilast corticosteroid step",
        "non biologic therapy topical agent conventional synthetic drug trial failure tnf blocker",
    ),
    "step_through_phototherapy": (
        "phototherapy puva ultraviolet uvb light therapy required trial failure",
        "member must use phototherapy before requested drug",
    ),
    "tb_test_required": (
        "tuberculosis tb test screening tst igra negative test before initiating therapy",
        "documented negative tuberculosis test within months",
    ),
    "initial_auth_duration": (
        "initial authorization duration approval duration coverage duration initial therapy months",
        "authorization may be granted approved for months initial request",
    ),
    "reauthorization_duration": (
        "reauthorization duration renewal duration continuation approval continued therapy months",
        "continued authorization may be granted approved for months",
    ),
    "reauthorization_required": (
        "reauthorization renewal continuation continued therapy requires criteria after initial approval",
        "initial therapy continuation therapy must meet renewal criteria",
    ),
    "reauthorization_requirements": (
        "reauthorization requirements continued therapy continuation clinical response improvement chart notes disease activity",
        "renewal requires positive response no unacceptable toxicity",
    ),
    "specialist_types": (
        "specialist prescriber dermatologist rheumatologist prescribed by consultation with",
        "prescriber restriction physician specialist provider type",
    ),
    "quantity_limits": (
        "quantity limit ql maximum quantity units per days syringes pens vials per month",
        "maximum dose quantity per fill per authorization period",
    ),
}


def retrieve_policy_context(
    chunks: Sequence[PolicyChunk],
    brand: str,
    indication: str = "Psoriasis",
    max_chunks: int = 14,
    brand_aliases: Mapping[str, Sequence[str]] | None = None,
    extra_drug_terms: Sequence[str] = (),
) -> List[PolicyChunk]:
    tagged_chunks = [tag_chunk(chunk, brand, indication, brand_aliases, extra_drug_terms) for chunk in chunks]
    tagged_chunks = [chunk for chunk in tagged_chunks if not _is_ignored_chunk(chunk)]
    scored = [(score_chunk(chunk, brand, indication, brand_aliases), chunk) for chunk in tagged_chunks]

    selected = [chunk for score, chunk in sorted(scored, key=lambda item: item[0], reverse=True) if score > 0]

    # Keep high-value universal clauses even when brand text is sparse.
    selected = _dedupe_chunks(selected)
    return selected[:max_chunks]


def retrieve_rule_aware_context(
    chunks: Sequence[PolicyChunk],
    brand: str,
    indication: str = "Psoriasis",
    max_global_chunks: int = 2,
    max_chunks_per_field: int = 1,
    brand_aliases: Mapping[str, Sequence[str]] | None = None,
    extra_drug_terms: Sequence[str] = (),
) -> Dict[str, List[PolicyChunk]]:
    tagged_chunks = [tag_chunk(chunk, brand, indication, brand_aliases, extra_drug_terms) for chunk in chunks]
    tagged_chunks = [chunk for chunk in tagged_chunks if not _is_ignored_chunk(chunk)]

    global_chunks = _rank_for_scope(tagged_chunks, brand, indication, brand_aliases)[:max_global_chunks]
    universal_chunks = [
        chunk
        for chunk in _rank_for_scope(tagged_chunks, brand, indication, brand_aliases)
        if "universal" in chunk.tags
    ][:1]

    context: Dict[str, List[PolicyChunk]] = {"global_applicability": global_chunks}
    for field_name in FIELD_TO_RULE_FILE:
        field_chunks = _rank_for_field(tagged_chunks, brand, indication, field_name, brand_aliases)
        field_chunks = _dedupe_chunks(universal_chunks + field_chunks)
        context[field_name] = field_chunks[:max_chunks_per_field]

    return context


def retrieve_parameter_context(
    chunks: Sequence[PolicyChunk],
    brand: str,
    field_name: str,
    indication: str = "Psoriasis",
    max_chunks: int = 3,
    brand_aliases: Mapping[str, Sequence[str]] | None = None,
    extra_drug_terms: Sequence[str] = (),
) -> List[PolicyChunk]:
    tagged_chunks = [tag_chunk(chunk, brand, indication, brand_aliases, extra_drug_terms) for chunk in chunks]
    tagged_chunks = [chunk for chunk in tagged_chunks if not _is_ignored_chunk(chunk)]
    universal_chunks = [
        chunk
        for chunk in _rank_for_scope(tagged_chunks, brand, indication, brand_aliases)
        if "universal" in chunk.tags
    ][:1]
    field_chunks = _rank_for_field(tagged_chunks, brand, indication, field_name, brand_aliases)
    return _dedupe_chunks(universal_chunks + field_chunks)[:max_chunks]


def tag_chunk(
    chunk: PolicyChunk,
    brand: str,
    indication: str = "Psoriasis",
    brand_aliases: Mapping[str, Sequence[str]] | None = None,
    extra_drug_terms: Sequence[str] = (),
) -> PolicyChunk:
    text = _normalize(f"{chunk.title}\n{chunk.text}")
    aliases = _aliases_for_brand(brand, brand_aliases)
    drug_terms = _drug_terms(extra_drug_terms)

    if _contains_any(text, aliases):
        chunk.tags.add("brand")
    if _contains_any(text, INDICATION_ALIASES) or indication.lower() in text:
        chunk.tags.add("indication")
    if _contains_any(text, UNIVERSAL_TERMS):
        chunk.tags.add("universal")
    if _contains_any(text, (*PARAMETER_TERMS, *extra_drug_terms)):
        chunk.tags.add("parameter")
    if _contains_any(text, APPROVAL_TERMS):
        chunk.tags.add("approval")
    if _contains_any(text, DENIAL_TERMS):
        chunk.tags.add("denial")
    if _contains_any(text, DURATION_TERMS):
        chunk.tags.add("duration")
    if _contains_any(text, SAFETY_TERMS):
        chunk.tags.add("safety")
    if _contains_any(text, drug_terms):
        chunk.tags.add("drug_or_therapy")
    if _contains_any(text, ("reauthorization", "renewal", "continuation", "continued therapy")):
        chunk.tags.add("reauthorization")
    if _contains_any(text, ("quantity limit", "ql", "maximum quantity", "units per")):
        chunk.tags.add("quantity_limit")

    return chunk


def score_chunk(
    chunk: PolicyChunk,
    brand: str,
    indication: str = "Psoriasis",
    brand_aliases: Mapping[str, Sequence[str]] | None = None,
) -> float:
    text = _normalize(f"{chunk.title}\n{chunk.text}")
    aliases = _aliases_for_brand(brand, brand_aliases)
    token_counts = Counter(_tokens(text))

    score = 0.0
    score += 8.0 if "brand" in chunk.tags else 0.0
    score += 6.0 if "indication" in chunk.tags else 0.0
    score += 5.0 if "universal" in chunk.tags else 0.0
    score += 3.0 if "parameter" in chunk.tags else 0.0
    score += 2.0 if "approval" in chunk.tags else 0.0
    score += 1.0 if "drug_or_therapy" in chunk.tags else 0.0
    score += 2.0 if "reauthorization" in chunk.tags else 0.0
    score += 2.0 if "quantity_limit" in chunk.tags else 0.0
    score += 2.0 if "duration" in chunk.tags else 0.0

    for alias in aliases:
        score += 3.0 * text.count(alias)
    for alias in INDICATION_ALIASES:
        score += 1.5 * text.count(alias)

    for query in PARAMETER_QUERIES:
        score += _cosine_token_overlap(token_counts, _tokens(query))

    unrelated_indications = ("crohn", "ulcerative colitis", "psoriatic arthritis", "rheumatoid arthritis")
    if "brand" not in chunk.tags and _contains_any(text, unrelated_indications):
        score -= 4.0

    return score


def score_chunk_for_field(
    chunk: PolicyChunk,
    brand: str,
    indication: str,
    field_name: str,
    brand_aliases: Mapping[str, Sequence[str]] | None = None,
) -> float:
    text = _normalize(f"{chunk.title}\n{chunk.text}")
    token_counts = Counter(_tokens(text))
    score = score_chunk(chunk, brand, indication, brand_aliases) * 0.35

    for query in FIELD_QUERIES.get(field_name, ()):
        score += 8.0 * _cosine_token_overlap(token_counts, _tokens(query))

    if "universal" in chunk.tags and field_name in {
        "step_therapy_requirements",
        "number_of_steps_brands",
        "number_of_steps_generic",
        "step_through_phototherapy",
        "tb_test_required",
        "initial_auth_duration",
        "reauthorization_duration",
        "reauthorization_required",
        "reauthorization_requirements",
        "quantity_limits",
    }:
        score += 4.0

    if field_name.startswith("reauthorization") and "reauthorization" in chunk.tags:
        score += 4.0
    if field_name == "quantity_limits" and "quantity_limit" in chunk.tags:
        score += 4.0
    if field_name in {"step_therapy_requirements", "number_of_steps_brands", "number_of_steps_generic"}:
        if "drug_or_therapy" in chunk.tags:
            score += 4.0
        if "approval" in chunk.tags:
            score += 3.0
    if field_name == "age" and _contains_any(text, ("fda labeled age", "fda-labelled age", "fda approved age")):
        score += 10.0
    if field_name == "step_through_phototherapy" and "phototherapy" in text:
        score += 8.0
        if _contains_any(text, ("concurrent phototherapy", "not receiving concurrent phototherapy", "concurrent therapy")):
            score += 5.0
    if field_name == "initial_auth_duration" and _contains_any(
        text,
        ("duration of approval", "initial approval", "initial authorization is", "initial authorization may"),
    ):
        score += 50.0
    if field_name == "reauthorization_duration" and _contains_any(
        text,
        ("duration of approval", "reauthorization approval", "reauthorization", "renewal approval"),
    ):
        score += 50.0

    return score


def format_chunks_for_prompt(chunks: Iterable[PolicyChunk], max_chars_per_chunk: int = 700) -> str:
    formatted = []
    for chunk in chunks:
        tags = ", ".join(sorted(chunk.tags)) or "none"
        text = _trim_text(chunk.text, max_chars_per_chunk)
        formatted.append(
            f"[{chunk.chunk_id} | lines {chunk.start_line}-{chunk.end_line} | tags: {tags} | title: {chunk.title}]\n"
            f"{text}"
        )
    return "\n\n---\n\n".join(formatted)


def format_context_pack_for_prompt(
    context: Dict[str, Sequence[PolicyChunk]],
    max_chars_per_chunk: int = 700,
) -> str:
    sections = []
    for field_name, chunks in context.items():
        sections.append(
            f"### {field_name}\n{format_chunks_for_prompt(chunks, max_chars_per_chunk=max_chars_per_chunk)}"
        )
    return "\n\n".join(sections)


def _rank_for_scope(
    chunks: Sequence[PolicyChunk],
    brand: str,
    indication: str,
    brand_aliases: Mapping[str, Sequence[str]] | None = None,
) -> List[PolicyChunk]:
    scored = [(score_chunk(chunk, brand, indication, brand_aliases), chunk) for chunk in chunks]
    return [
        chunk
        for score, chunk in sorted(scored, key=lambda item: item[0], reverse=True)
        if score > 0
    ]


def _rank_for_field(
    chunks: Sequence[PolicyChunk],
    brand: str,
    indication: str,
    field_name: str,
    brand_aliases: Mapping[str, Sequence[str]] | None = None,
) -> List[PolicyChunk]:
    scored = [
        (score_chunk_for_field(chunk, brand, indication, field_name, brand_aliases), chunk)
        for chunk in chunks
    ]
    return [
        chunk
        for score, chunk in sorted(scored, key=lambda item: item[0], reverse=True)
        if score > 1.0
    ]


def _cosine_token_overlap(document_counts: Counter, query_tokens: List[str]) -> float:
    query_counts = Counter(query_tokens)
    if not document_counts or not query_counts:
        return 0.0

    dot = sum(document_counts[token] * query_counts[token] for token in query_counts)
    doc_norm = math.sqrt(sum(value * value for value in document_counts.values()))
    query_norm = math.sqrt(sum(value * value for value in query_counts.values()))
    return dot / (doc_norm * query_norm)


def _dedupe_chunks(chunks: Sequence[PolicyChunk]) -> List[PolicyChunk]:
    seen = set()
    deduped = []
    for chunk in chunks:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        deduped.append(chunk)
    return deduped


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term.lower() in text for term in terms)


def _aliases_for_brand(
    brand: str,
    brand_aliases: Mapping[str, Sequence[str]] | None = None,
) -> Sequence[str]:
    aliases = set(BRAND_ALIASES.get(brand.upper(), (brand.lower(),)))
    aliases.add(brand.lower())
    if brand_aliases:
        aliases.update(alias.lower() for alias in brand_aliases.get(brand.upper(), ()))
        aliases.update(alias.lower() for alias in brand_aliases.get(brand, ()))
    return tuple(sorted(alias for alias in aliases if alias))


def _drug_terms(extra_drug_terms: Sequence[str] = ()) -> Sequence[str]:
    terms = set(DRUG_AND_THERAPY_TERMS)
    terms.update(term.lower() for term in extra_drug_terms)
    return tuple(sorted(term for term in terms if term))


def _is_ignored_chunk(chunk: PolicyChunk) -> bool:
    title = _normalize(chunk.title)
    if _contains_any(title, IGNORED_SECTION_TERMS):
        return True
    return False


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _trim_text(text: str, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rsplit(" ", 1)[0] + " ..."
