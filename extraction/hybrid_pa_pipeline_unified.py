import csv
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from extraction.llm_client import call_llm_text, resolve_model, resolve_provider
from extraction.unified_chunk_retrieval import (
    UnifiedChunk,
    build_parameter_queries,
    build_unified_chunks,
    keyword_score,
    locate_input_files,
    load_first_submission,
)


BASE_DIR = Path(__file__).resolve().parents[1]
SUBMISSIONS_CSV = BASE_DIR / "submissions.csv"
PARAMETER_REFERENCE = BASE_DIR / "output_test" / "llm_parameter_understanding.md"
OUTPUT_SCHEMA_FILE = BASE_DIR / "output_schema.py"
OUTPUT_DIR = BASE_DIR / "output_test"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_schema_keys() -> list[str]:
    namespace: dict[str, Any] = {}
    exec(OUTPUT_SCHEMA_FILE.read_text(encoding="utf-8"), namespace)
    schema = namespace.get("schema", {})
    if not isinstance(schema, dict):
        raise RuntimeError("output_schema.py must define a dict named 'schema'.")
    return list(schema.keys())


def parse_parameter_reference() -> dict[str, str]:
    raw = PARAMETER_REFERENCE.read_text(encoding="utf-8", errors="ignore")
    sections = re.split(r"(?m)^## Parameter \d+:\s+", raw)
    parameter_map: dict[str, str] = {}
    for section in sections[1:]:
        heading_line, _, body = section.partition("\n")
        name_match = re.search(r"`([^`]+)`", heading_line)
        if not name_match:
            continue
        parameter_map[name_match.group(1)] = body.strip()
    return parameter_map


def normalize_whitespace(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text.replace("\x00", " ")).strip()


def build_hybrid_retrieval(
    chunks: list[UnifiedChunk], brand_name: str, parameter_queries: dict[str, str], top_k: int = 4
) -> dict[str, Any]:
    query_items = [f"{brand_name} prior authorization criteria"] + list(parameter_queries.values())
    texts = [chunk.text for chunk in chunks]
    from sklearn.feature_extraction.text import TfidfVectorizer

    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(texts + query_items)
    chunk_matrix = matrix[: len(chunks)]
    query_matrix = matrix[len(chunks) :]

    overall_scores = (chunk_matrix @ query_matrix[0].T).toarray().ravel()
    retrieved: dict[str, Any] = {"overall": [], "by_parameter": {}}

    ranked_overall = []
    for idx, chunk in enumerate(chunks):
        semantic = float(overall_scores[idx])
        keyword = keyword_score(chunk.text, query_items[0])
        source_boost = 0.15 if chunk.source_type == "table" else 0.0
        brand_boost = 0.2 if brand_name.lower() in chunk.text.lower() else 0.0
        score = semantic + keyword + source_boost + brand_boost
        ranked_overall.append((score, idx, semantic, keyword, source_boost, brand_boost))
    ranked_overall.sort(reverse=True)

    for score, idx, semantic, keyword, source_boost, brand_boost in ranked_overall[:top_k]:
        retrieved["overall"].append(
            {
                "chunk_id": chunks[idx].chunk_id,
                "source_type": chunks[idx].source_type,
                "score": round(score, 4),
                "semantic_score": round(semantic, 4),
                "keyword_score": round(keyword, 4),
                "source_boost": round(source_boost, 4),
                "brand_boost": round(brand_boost, 4),
            }
        )

    for q_idx, (parameter, query) in enumerate(parameter_queries.items(), start=1):
        param_scores = (chunk_matrix @ query_matrix[q_idx].T).toarray().ravel()
        ranked = []
        for idx, chunk in enumerate(chunks):
            semantic = float(param_scores[idx])
            keyword = keyword_score(chunk.text, query)
            source_boost = 0.15 if chunk.source_type == "table" else 0.0
            score = semantic + keyword + source_boost
            ranked.append((score, idx, semantic, keyword, source_boost))
        ranked.sort(reverse=True)
        retrieved["by_parameter"][parameter] = [
            {
                "chunk_id": chunks[idx].chunk_id,
                "source_type": chunks[idx].source_type,
                "score": round(score, 4),
                "semantic_score": round(semantic, 4),
                "keyword_score": round(keyword, 4),
                "source_boost": round(source_boost, 4),
            }
            for score, idx, semantic, keyword, source_boost in ranked[:top_k]
        ]
    return retrieved


def collect_retrieved_chunks(chunks: list[UnifiedChunk], retrieval: dict[str, Any]) -> list[UnifiedChunk]:
    chunk_ids: set[str] = {item["chunk_id"] for item in retrieval["overall"]}
    for items in retrieval["by_parameter"].values():
        for item in items:
            chunk_ids.add(item["chunk_id"])
    return [chunk for chunk in chunks if chunk.chunk_id in chunk_ids]


def build_extraction_context(
    brand_name: str,
    parameter_reference_text: str,
    schema_keys: list[str],
    retrieved_chunks: list[UnifiedChunk],
) -> str:
    context = {
        "brand_name": brand_name,
        "required_schema_keys": schema_keys,
        "parameter_reference": parameter_reference_text,
        "retrieved_chunks": [
            {
                "chunk_id": chunk.chunk_id,
                "source_type": chunk.source_type,
                "section_title": chunk.section_title,
                "page_number": chunk.page_number,
                "heading_path": chunk.heading_path,
                "quality_flags": chunk.quality_flags,
                "text": chunk.text,
                "metadata": chunk.metadata,
            }
            for chunk in retrieved_chunks
        ],
    }
    return json.dumps(context, indent=2, ensure_ascii=False)


def parse_llm_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise RuntimeError("LLM output must be a JSON object.")
    return parsed


def call_llm_for_extraction(prompt: str) -> dict[str, Any]:
    provider = resolve_provider()
    model_name = resolve_model(provider)
    text = call_llm_text(
        prompt,
        provider=provider,
        model=model_name,
        temperature=0.0,
        top_p=0.1,
        max_tokens=4096,
        json_mode=True,
    )
    return parse_llm_json(text)


def validate_and_normalize(result: dict[str, Any], schema_keys: list[str], filename: str, brand_name: str) -> dict[str, Any]:
    structured = result.get("final_structured_json", {})
    if not isinstance(structured, dict):
        structured = {}
    normalized = {key: structured.get(key) for key in schema_keys}
    normalized["filename"] = filename
    normalized["brand"] = brand_name
    result["final_structured_json"] = normalized
    return result


def build_llm_prompt(extraction_context: str) -> str:
    return (
        "You are extracting structured data from a US payer prior authorization document.\n"
        "Use only the supplied evidence. Never hallucinate. If evidence is missing, return null.\n"
        "Return a single JSON object with exactly these top-level keys:\n"
        "- final_structured_json\n"
        "- source_provenance_mappings\n"
        "- reasoning_summary\n"
        f"Context:\n{extraction_context}"
    )


def run_pipeline() -> dict[str, Any]:
    first_row = load_first_submission()
    filename = first_row["Filename"]
    brand_name = first_row["Brand"]
    markdown_path, pdf_path = locate_input_files(filename)
    parameter_reference_text = PARAMETER_REFERENCE.read_text(encoding="utf-8", errors="ignore")
    schema_keys = load_schema_keys()
    parameter_map = parse_parameter_reference()

    chunks = build_unified_chunks(filename, brand_name, markdown_path, pdf_path)
    parameter_queries = build_parameter_queries(brand_name)
    retrieval = build_hybrid_retrieval(chunks, brand_name, parameter_queries)
    retrieved_chunks = collect_retrieved_chunks(chunks, retrieval)
    extraction_context = build_extraction_context(brand_name, parameter_reference_text, schema_keys, retrieved_chunks)

    llm_error = None
    try:
        extraction_result = call_llm_for_extraction(build_llm_prompt(extraction_context))
    except Exception as exc:
        llm_error = f"{type(exc).__name__}: {exc}"
        extraction_result = {
            "final_structured_json": {key: None for key in schema_keys},
            "source_provenance_mappings": {},
            "reasoning_summary": [],
            "debug_notes": [f"LLM failed: {llm_error}"],
        }

    extraction_result = validate_and_normalize(extraction_result, schema_keys, filename, brand_name)
    extraction_result["retrieved_chunks"] = [asdict(chunk) for chunk in retrieved_chunks]
    extraction_result["debug_metadata"] = {
        "processed_filename": filename,
        "brand_name": brand_name,
        "retrieved_chunk_count": len(retrieved_chunks),
        "llm_provider": resolve_provider(),
        "llm_model": resolve_model(resolve_provider()),
        "llm_error": llm_error,
        "source_counts": {
            "docling_md": sum(1 for chunk in chunks if chunk.source_type == "docling_md"),
            "pdfplumber_text": sum(1 for chunk in chunks if chunk.source_type == "pdfplumber_text"),
            "table": sum(1 for chunk in chunks if chunk.source_type == "table"),
            "fitz_fallback": sum(1 for chunk in chunks if chunk.source_type == "fitz_fallback"),
        },
        "retrieval_scores": retrieval,
    }
    return extraction_result


def main() -> None:
    result = run_pipeline()
    output_file = OUTPUT_DIR / "hybrid_pa_pipeline_unified_first_doc.json"
    output_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(str(output_file))


if __name__ == "__main__":
    main()
