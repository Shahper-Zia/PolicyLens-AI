import csv
import json
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import fitz
import pdfplumber
from openai import OpenAI
from sklearn.feature_extraction.text import TfidfVectorizer


BASE_DIR = Path(__file__).resolve().parents[1]
SUBMISSIONS_CSV = BASE_DIR / "submissions.csv"
RAW_MARKDOWN_DIR = BASE_DIR / "data" / "extracted_pdfs" / "raw_markdown"
RAW_PDF_DIR = BASE_DIR / "data" / "raw_pdfs"
PARAMETER_REFERENCE = BASE_DIR / "output_test" / "llm_parameter_understanding.md"
OUTPUT_SCHEMA_FILE = BASE_DIR / "output_schema.py"
OUTPUT_DIR = BASE_DIR / "output_test"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ENV_FILE = BASE_DIR / ".env"

DEFAULT_LLM_PROVIDER = "groq"
DEFAULT_MODEL = "llama-3.3-70b-versatile"
DEFAULT_API_URL = "https://api.groq.com/openai/v1"


@dataclass
class Chunk:
    filename: str
    brand_name: str
    chunk_id: str
    section_title: str
    page_number: int | None
    text: str
    heading_path: list[str]
    markdown_quality_flags: list[str]


def load_dotenv_value(key: str) -> str:
    if not ENV_FILE.exists():
        return ""

    for line in ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return ""


def load_schema_keys() -> list[str]:
    namespace: dict[str, Any] = {}
    exec(OUTPUT_SCHEMA_FILE.read_text(encoding="utf-8"), namespace)
    schema = namespace.get("schema", {})
    if not isinstance(schema, dict):
        raise RuntimeError("output_schema.py must define a dict named 'schema'.")
    return list(schema.keys())


def load_first_submission() -> dict[str, str]:
    with SUBMISSIONS_CSV.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        first_row = next(reader, None)
    if not first_row:
        raise RuntimeError("submissions.csv is empty.")
    return first_row


def locate_input_files(filename: str) -> tuple[Path, Path]:
    pdf_path = RAW_PDF_DIR / filename
    markdown_path = RAW_MARKDOWN_DIR / Path(filename).with_suffix(".md").name
    if not markdown_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {markdown_path}")
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    return markdown_path, pdf_path


def normalize_whitespace(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text.replace("\x00", " ")).strip()


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


def parse_markdown_pages(markdown_text: str) -> list[tuple[int | None, str]]:
    pattern = re.compile(r"(?m)^Page:\s*$\s*^(?P<num>\d+)\s+of\s+\d+\s*$")
    matches = list(pattern.finditer(markdown_text))
    if not matches:
        return [(None, markdown_text)]

    pages: list[tuple[int | None, str]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(markdown_text)
        page_number = int(match.group("num"))
        pages.append((page_number, markdown_text[start:end].strip()))
    return pages


def chunk_markdown(markdown_text: str, filename: str, brand_name: str) -> list[Chunk]:
    pages = parse_markdown_pages(markdown_text)
    chunks: list[Chunk] = []
    chunk_counter = 1

    for page_number, page_text in pages:
        lines = page_text.splitlines()
        current_heading = "Document"
        heading_path: list[str] = []
        block_lines: list[str] = []

        def flush_block() -> None:
            nonlocal chunk_counter, block_lines
            text = "\n".join(block_lines).strip()
            if not text:
                block_lines = []
                return
            flags = detect_markdown_quality_flags(text)
            chunks.append(
                Chunk(
                    filename=filename,
                    brand_name=brand_name,
                    chunk_id=f"chunk_{chunk_counter}",
                    section_title=current_heading,
                    page_number=page_number,
                    text=text,
                    heading_path=list(heading_path),
                    markdown_quality_flags=flags,
                )
            )
            chunk_counter += 1
            block_lines = []

        for line in lines:
            stripped = line.strip()
            if re.match(r"^##+\s+", stripped):
                flush_block()
                heading_text = re.sub(r"^##+\s+", "", stripped).strip()
                current_heading = heading_text or current_heading
                heading_path = [current_heading]
                block_lines.append(stripped)
                continue

            if not stripped:
                if block_lines and any(token in block_lines[-1] for token in ("|", "-", "o ", ":")):
                    block_lines.append("")
                else:
                    flush_block()
                continue

            block_lines.append(line)

        flush_block()

    return merge_small_chunks(chunks)


def merge_small_chunks(chunks: list[Chunk], min_chars: int = 220, max_chars: int = 2600) -> list[Chunk]:
    if not chunks:
        return []

    merged: list[Chunk] = []
    pending: Chunk | None = None

    for chunk in chunks:
        if pending is None:
            pending = chunk
            continue

        same_section = (
            pending.page_number == chunk.page_number
            and pending.section_title == chunk.section_title
        )
        combined_len = len(pending.text) + len(chunk.text) + 2

        if (len(pending.text) < min_chars or same_section) and combined_len <= max_chars:
            pending = Chunk(
                filename=pending.filename,
                brand_name=pending.brand_name,
                chunk_id=pending.chunk_id,
                section_title=pending.section_title,
                page_number=pending.page_number,
                text=f"{pending.text}\n\n{chunk.text}".strip(),
                heading_path=pending.heading_path,
                markdown_quality_flags=sorted(set(pending.markdown_quality_flags + chunk.markdown_quality_flags)),
            )
        else:
            merged.append(pending)
            pending = chunk

    if pending is not None:
        merged.append(pending)

    for idx, chunk in enumerate(merged, start=1):
        chunk.chunk_id = f"chunk_{idx}"
    return merged


def detect_markdown_quality_flags(text: str) -> list[str]:
    flags: list[str] = []
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return ["empty"]

    if "â" in text or "�" in text:
        flags.append("encoding_artifacts")
    if text.count("<!-- image -->") >= 1:
        flags.append("image_placeholder")
    if sum(1 for line in lines if line.strip().startswith("|")) >= 2:
        flags.append("markdown_table")
    if sum(1 for line in lines if line.strip().startswith("-")) >= 8 and len(lines) >= 10:
        flags.append("dense_list_or_flattened_table")
    if sum(1 for line in lines if len(line.strip()) <= 3) >= 4:
        flags.append("fragmented_lines")
    if any(term in text.lower() for term in ("quantity level limit", "dosage and administration", "approval duration")):
        flags.append("high_value_layout_section")
    return flags


def build_parameter_queries(parameter_map: dict[str, str], brand_name: str) -> dict[str, str]:
    queries: dict[str, str] = {}
    for parameter, details in parameter_map.items():
        summary = details.splitlines()[0] if details else parameter
        queries[parameter] = f"{brand_name} {parameter} {summary}"
    return queries


def keyword_score(text: str, query: str) -> float:
    text_l = text.lower()
    tokens = [token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 2]
    if not tokens:
        return 0.0
    hits = sum(1 for token in tokens if token in text_l)
    return hits / len(tokens)


def build_hybrid_retrieval(
    chunks: list[Chunk], brand_name: str, parameter_queries: dict[str, str], top_k: int = 4
) -> dict[str, Any]:
    texts = [chunk.text for chunk in chunks]
    query_items = [f"{brand_name} prior authorization criteria"] + list(parameter_queries.values())
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(texts + query_items)
    chunk_matrix = matrix[: len(chunks)]
    query_matrix = matrix[len(chunks) :]

    overall_scores = (chunk_matrix @ query_matrix[0].T).toarray().ravel()
    retrieved: dict[str, Any] = {
        "overall": [],
        "by_parameter": {},
    }

    overall_ranked = []
    for idx, chunk in enumerate(chunks):
        semantic = float(overall_scores[idx])
        keyword = keyword_score(chunk.text, query_items[0])
        brand_boost = 0.2 if brand_name.lower() in chunk.text.lower() else 0.0
        score = semantic + keyword + brand_boost
        overall_ranked.append((score, idx, semantic, keyword, brand_boost))

    overall_ranked.sort(reverse=True)
    for score, idx, semantic, keyword, brand_boost in overall_ranked[:top_k]:
        retrieved["overall"].append(
            {
                "chunk_id": chunks[idx].chunk_id,
                "score": round(score, 4),
                "semantic_score": round(semantic, 4),
                "keyword_score": round(keyword, 4),
                "brand_boost": round(brand_boost, 4),
            }
        )

    for query_idx, (parameter, query) in enumerate(parameter_queries.items(), start=1):
        param_scores = (chunk_matrix @ query_matrix[query_idx].T).toarray().ravel()
        ranked = []
        for idx, chunk in enumerate(chunks):
            semantic = float(param_scores[idx])
            keyword = keyword_score(chunk.text, query)
            score = semantic + keyword
            if parameter == "Step Therapy Requirements Documented in Policy" and "preferred products" in chunk.text.lower():
                score += 0.25
            ranked.append((score, idx, semantic, keyword))
        ranked.sort(reverse=True)
        retrieved["by_parameter"][parameter] = [
            {
                "chunk_id": chunks[idx].chunk_id,
                "score": round(score, 4),
                "semantic_score": round(semantic, 4),
                "keyword_score": round(keyword, 4),
            }
            for score, idx, semantic, keyword in ranked[:top_k]
        ]

    return retrieved


def collect_retrieved_chunks(chunks: list[Chunk], retrieval: dict[str, Any]) -> list[Chunk]:
    chunk_ids: set[str] = {item["chunk_id"] for item in retrieval["overall"]}
    for items in retrieval["by_parameter"].values():
        for item in items:
            chunk_ids.add(item["chunk_id"])
    return [chunk for chunk in chunks if chunk.chunk_id in chunk_ids]


def identify_pdf_fallback_pages(retrieved_chunks: list[Chunk], parameter_queries: dict[str, str]) -> list[dict[str, Any]]:
    page_reasons: dict[int, set[str]] = {}
    important_terms = {
        "Number of Steps through Brands": ["preferred products", "step", "ustekinumab", "adalimumab"],
        "Number of Steps through Generic": ["methotrexate", "cyclosporine", "acitretin", "topical"],
        "Step through-Phototherapy": ["phototherapy", "puva", "uvb"],
        "Quantity Limits": ["quantity level limit", "quantity", "exception limit"],
        "TB Test required": ["tuberculosis", "tb test", "igra", "tst"],
    }

    for chunk in retrieved_chunks:
        text_l = chunk.text.lower()
        reasons = set(chunk.markdown_quality_flags)
        for parameter, terms in important_terms.items():
            if any(term in text_l for term in terms) and any(
                flag in chunk.markdown_quality_flags
                for flag in ("encoding_artifacts", "dense_list_or_flattened_table", "high_value_layout_section", "fragmented_lines")
            ):
                reasons.add(f"suspect_{parameter.lower().replace(' ', '_')}")

        if reasons and chunk.page_number is not None:
            page_reasons.setdefault(chunk.page_number, set()).update(reasons)

    return [
        {
            "page_number": page_number,
            "reasons": sorted(reasons),
            "queries_considered": list(parameter_queries.keys()),
        }
        for page_number, reasons in sorted(page_reasons.items())
    ]


def extract_pdf_page_bundle(pdf_path: Path, fallback_pages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    extracted_sections: list[dict[str, Any]] = []
    extracted_tables: list[dict[str, Any]] = []
    if not fallback_pages:
        return extracted_sections, extracted_tables

    pages_needed = {item["page_number"] for item in fallback_pages if item.get("page_number")}
    page_reason_map = {item["page_number"]: item["reasons"] for item in fallback_pages if item.get("page_number")}

    with pdfplumber.open(pdf_path) as pdf:
        for page_number in sorted(pages_needed):
            page = pdf.pages[page_number - 1]
            raw_text = page.extract_text(layout=True) or ""
            tables = page.extract_tables() or []
            extracted_sections.append(
                {
                    "section_id": f"pdf_page_{page_number}",
                    "page_number": page_number,
                    "reasons": page_reason_map.get(page_number, []),
                    "text": raw_text.strip(),
                }
            )
            for table_index, table in enumerate(tables, start=1):
                rows = []
                for row in table:
                    if not row:
                        continue
                    cleaned = [normalize_whitespace(cell or "") for cell in row]
                    if any(cleaned):
                        rows.append(cleaned)
                if rows:
                    extracted_tables.append(
                        {
                            "page_number": page_number,
                            "table_id": f"page_{page_number}_table_{table_index}",
                            "rows": rows,
                        }
                    )

    if extracted_sections and not any(section["text"] for section in extracted_sections):
        extracted_sections = extract_pdf_with_fitz(pdf_path, sorted(pages_needed), page_reason_map)

    return extracted_sections, extracted_tables


def extract_pdf_with_fitz(
    pdf_path: Path, pages_needed: list[int], page_reason_map: dict[int, list[str]]
) -> list[dict[str, Any]]:
    doc = fitz.open(pdf_path)
    sections: list[dict[str, Any]] = []
    try:
        for page_number in pages_needed:
            page = doc.load_page(page_number - 1)
            sections.append(
                {
                    "section_id": f"pdf_page_{page_number}",
                    "page_number": page_number,
                    "reasons": page_reason_map.get(page_number, []),
                    "text": page.get_text("text").strip(),
                }
            )
    finally:
        doc.close()
    return sections


def build_extraction_context(
    brand_name: str,
    parameter_reference_text: str,
    schema_keys: list[str],
    retrieved_chunks: list[Chunk],
    pdf_sections: list[dict[str, Any]],
    extracted_tables: list[dict[str, Any]],
) -> str:
    chunk_payload = [
        {
            "chunk_id": chunk.chunk_id,
            "section_title": chunk.section_title,
            "page_number": chunk.page_number,
            "heading_path": chunk.heading_path,
            "text": chunk.text,
        }
        for chunk in retrieved_chunks
    ]

    context = {
        "brand_name": brand_name,
        "required_schema_keys": schema_keys,
        "parameter_reference": parameter_reference_text,
        "retrieved_markdown_chunks": chunk_payload,
        "pdf_fallback_sections": pdf_sections,
        "extracted_tables": extracted_tables,
    }
    return json.dumps(context, indent=2, ensure_ascii=False)


def call_llm_for_extraction(prompt: str) -> dict[str, Any]:
    provider = (os.getenv("LLM_PROVIDER") or load_dotenv_value("LLM_PROVIDER") or DEFAULT_LLM_PROVIDER).strip().lower()
    api_key = (
        os.getenv("GROQ_API_KEY")
        or load_dotenv_value("GROQ_API_KEY")
        or os.getenv("LLAMA_API_KEY")
        or load_dotenv_value("LLAMA_API_KEY")
    ).strip()
    model_name = (
        os.getenv("GROQ_MODEL")
        or load_dotenv_value("GROQ_MODEL")
        or os.getenv("LLAMA_MODEL")
        or load_dotenv_value("LLAMA_MODEL")
        or DEFAULT_MODEL
    ).strip()
    api_url = (
        os.getenv("GROQ_API_URL")
        or load_dotenv_value("GROQ_API_URL")
        or os.getenv("LLAMA_API_URL")
        or load_dotenv_value("LLAMA_API_URL")
        or DEFAULT_API_URL
    ).strip()
    if provider not in {"groq", "llama"}:
        raise RuntimeError(f"Unsupported LLM_PROVIDER for extraction pipeline: {provider}")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY or LLAMA_API_KEY is not configured.")

    client = OpenAI(api_key=api_key, base_url=api_url)
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            top_p=0.1,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        raise RuntimeError(f"LLM API failed: {exc}") from exc

    text = (response.choices[0].message.content or "").strip()
    return parse_llm_json(text)


def parse_llm_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Could not parse LLM JSON output: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("LLM output must be a JSON object.")
    return parsed


def heuristic_extraction(
    filename: str,
    brand_name: str,
    chunks: list[Chunk],
    pdf_sections: list[dict[str, Any]],
    extracted_tables: list[dict[str, Any]],
    schema_keys: list[str],
) -> dict[str, Any]:
    combined_text = "\n\n".join(chunk.text for chunk in chunks)
    result = {key: None for key in schema_keys}
    result["filename"] = filename
    result["brand"] = brand_name
    result["access_score"] = None

    age_match = re.search(r"treatment of adult patients|for adult members|in adults", combined_text, flags=re.IGNORECASE)
    if age_match:
        result["age"] = "FDA labelled age"

    step_chunk = next((chunk for chunk in chunks if "preferred products" in chunk.text.lower()), None)
    if step_chunk:
        result["step_therapy_requirements"] = normalize_whitespace(step_chunk.text)
        result["number_of_steps_brands"] = "3" if "three preferred products" in step_chunk.text.lower() else None
        result["number_of_steps_generic"] = "NA"

    if "phototherapy" in combined_text.lower():
        result["step_through_phototherapy"] = "No"

    if "negative tuberculosis" in combined_text.lower() or "tb test" in combined_text.lower():
        result["tb_test_required"] = "Y"

    specialist_match = re.search(
        r"## Prescriber Specialty:(?P<body>.*?)(?:## Coverage Criteria|## Dosage and Administration)",
        combined_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if specialist_match:
        result["specialist_types"] = normalize_whitespace(specialist_match.group("body"))

    duration_matches = re.findall(r"Authorization of (\d+) months", combined_text, flags=re.IGNORECASE)
    if duration_matches:
        result["initial_auth_duration"] = duration_matches[0]
        result["reauthorization_duration"] = duration_matches[0]
        result["reauthorization_required"] = "Yes"

    continuation_match = re.search(
        r"## Continuation of Therapy(?P<body>.*?)(?:## Other|## Dosage and Administration)",
        combined_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if continuation_match:
        result["reauthorization_requirements"] = normalize_whitespace(continuation_match.group("body"))

    table_rows = []
    for table in extracted_tables:
        if any("tremfya" in " ".join(row).lower() for row in table["rows"]):
            table_rows.extend(table["rows"])
    if table_rows:
        result["quantity_limits"] = "; ".join(" | ".join(row) for row in table_rows[:6])
    elif "quantity level limit" in combined_text.lower():
        quantity_match = re.search(
            r"## Quantity Level Limit:(?P<body>.*?)(?:## References:|$)",
            combined_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if quantity_match:
            result["quantity_limits"] = normalize_whitespace(quantity_match.group("body"))

    provenance = {
        key: {"method": "heuristic", "source_ids": []}
        for key in schema_keys
        if key not in {"filename", "brand"}
    }
    for chunk in chunks:
        text_l = chunk.text.lower()
        if "adult" in text_l:
            provenance["age"]["source_ids"].append(chunk.chunk_id)
        if "preferred products" in text_l:
            provenance["step_therapy_requirements"]["source_ids"].append(chunk.chunk_id)
            provenance["number_of_steps_brands"]["source_ids"].append(chunk.chunk_id)
            provenance["number_of_steps_generic"]["source_ids"].append(chunk.chunk_id)
        if "phototherapy" in text_l:
            provenance["step_through_phototherapy"]["source_ids"].append(chunk.chunk_id)
        if "tuberculosis" in text_l or "tb" in text_l:
            provenance["tb_test_required"]["source_ids"].append(chunk.chunk_id)
        if "prescriber specialty" in text_l:
            provenance["specialist_types"]["source_ids"].append(chunk.chunk_id)
        if "authorization of 12 months" in text_l:
            provenance["initial_auth_duration"]["source_ids"].append(chunk.chunk_id)
            provenance["reauthorization_duration"]["source_ids"].append(chunk.chunk_id)
        if "continuation requests" in text_l or "continuation of therapy" in text_l:
            provenance["reauthorization_requirements"]["source_ids"].append(chunk.chunk_id)
            provenance["reauthorization_required"]["source_ids"].append(chunk.chunk_id)
        if "quantity level limit" in text_l:
            provenance["quantity_limits"]["source_ids"].append(chunk.chunk_id)

    return {
        "final_structured_json": result,
        "source_provenance_mappings": provenance,
        "debug_notes": ["Heuristic fallback used because LLM extraction was unavailable."],
    }


def validate_final_output(result: dict[str, Any], schema_keys: list[str]) -> dict[str, Any]:
    structured = result.get("final_structured_json", {})
    if not isinstance(structured, dict):
        raise RuntimeError("final_structured_json must be an object.")

    normalized = {key: structured.get(key) for key in schema_keys}
    for key in schema_keys:
        normalized.setdefault(key, None)
    result["final_structured_json"] = normalized

    missing = [key for key in schema_keys if key not in structured]
    result.setdefault("debug_notes", [])
    if missing:
        result["debug_notes"].append(f"Missing schema keys normalized to null: {missing}")
    return result


def normalize_schema_values(
    result: dict[str, Any], filename: str, brand_name: str, schema_keys: list[str]
) -> dict[str, Any]:
    structured = result["final_structured_json"]
    structured["filename"] = filename
    structured["brand"] = brand_name

    if structured.get("tb_test_required") is not None:
        tb_value = str(structured["tb_test_required"]).strip().lower()
        if tb_value in {"yes", "y", "required", "true"}:
            structured["tb_test_required"] = "Y"
        elif tb_value in {"no", "n", "false"}:
            structured["tb_test_required"] = "No"

    for numeric_field in (
        "number_of_steps_brands",
        "number_of_steps_generic",
        "initial_auth_duration",
        "reauthorization_duration",
    ):
        if structured.get(numeric_field) is not None and structured[numeric_field] != "":
            structured[numeric_field] = str(structured[numeric_field])

    if structured.get("number_of_steps_generic") is None:
        step_text = structured.get("step_therapy_requirements") or ""
        if step_text:
            structured["number_of_steps_generic"] = "NA"

    for key in schema_keys:
        structured.setdefault(key, None)

    result["final_structured_json"] = structured
    return result


def build_llm_prompt(extraction_context: str) -> str:
    return (
        "You are extracting structured data from a US payer prior authorization document.\n"
        "You will receive only retrieved markdown chunks, PDF fallback sections, and extracted tables for one brand.\n"
        "Use only the supplied evidence. Never hallucinate. If evidence is missing, return null.\n"
        "Apply the rules from the parameter reference exactly, including Yes/No/NA semantics where defined.\n"
        "Return a single JSON object with exactly these top-level keys:\n"
        "- final_structured_json\n"
        "- source_provenance_mappings\n"
        "- reasoning_summary\n"
        "\n"
        "Requirements for final_structured_json:\n"
        "- Must include every required schema field exactly once.\n"
        "- Use null for missing values.\n"
        "- Preserve strings for fields such as age, step text, durations, and quantity limits.\n"
        "- filename and brand must be populated.\n"
        "\n"
        "Requirements for source_provenance_mappings:\n"
        "- Map each extracted field to a JSON object with keys: source_ids, page_numbers, evidence_snippets.\n"
        "- source_ids may include markdown chunk IDs like chunk_3 and PDF/table IDs like pdf_page_6 or page_6_table_1.\n"
        "- evidence_snippets must be short verbatim snippets from the provided context.\n"
        "\n"
        "reasoning_summary must be a short list of concise statements.\n"
        "\n"
        f"Context:\n{extraction_context}"
    )


def run_pipeline() -> dict[str, Any]:
    first_row = load_first_submission()
    filename = first_row["Filename"]
    brand_name = first_row["Brand"]
    markdown_path, pdf_path = locate_input_files(filename)
    markdown_text = markdown_path.read_text(encoding="utf-8", errors="ignore")
    parameter_reference_text = PARAMETER_REFERENCE.read_text(encoding="utf-8", errors="ignore")
    schema_keys = load_schema_keys()
    parameter_map = parse_parameter_reference()

    chunks = chunk_markdown(markdown_text, filename, brand_name)
    parameter_queries = build_parameter_queries(parameter_map, brand_name)
    retrieval = build_hybrid_retrieval(chunks, brand_name, parameter_queries)
    retrieved_chunks = collect_retrieved_chunks(chunks, retrieval)
    fallback_pages = identify_pdf_fallback_pages(retrieved_chunks, parameter_queries)
    pdf_sections, extracted_tables = extract_pdf_page_bundle(pdf_path, fallback_pages)

    extraction_context = build_extraction_context(
        brand_name=brand_name,
        parameter_reference_text=parameter_reference_text,
        schema_keys=schema_keys,
        retrieved_chunks=retrieved_chunks,
        pdf_sections=pdf_sections,
        extracted_tables=extracted_tables,
    )

    llm_error = None
    try:
        extraction_result = call_llm_for_extraction(build_llm_prompt(extraction_context))
    except Exception as exc:
        llm_error = f"{type(exc).__name__}: {exc}"
        extraction_result = heuristic_extraction(
            filename=filename,
            brand_name=brand_name,
            chunks=retrieved_chunks,
            pdf_sections=pdf_sections,
            extracted_tables=extracted_tables,
            schema_keys=schema_keys,
        )

    extraction_result = validate_final_output(extraction_result, schema_keys)
    extraction_result = normalize_schema_values(extraction_result, filename, brand_name, schema_keys)
    extraction_result["retrieved_markdown_chunks"] = [asdict(chunk) for chunk in retrieved_chunks]
    extraction_result["pdf_fallback_extracted_sections"] = pdf_sections
    extraction_result["extracted_tables"] = extracted_tables
    extraction_result["debug_metadata"] = {
        "processed_filename": filename,
        "brand_name": brand_name,
        "markdown_path": str(markdown_path),
        "pdf_path": str(pdf_path),
        "total_chunks_created": len(chunks),
        "retrieved_chunk_count": len(retrieved_chunks),
        "fallback_pages": fallback_pages,
        "retrieval_scores": retrieval,
        "llm_provider": os.getenv("LLM_PROVIDER") or load_dotenv_value("LLM_PROVIDER") or DEFAULT_LLM_PROVIDER,
        "llm_model": (
            os.getenv("GROQ_MODEL")
            or load_dotenv_value("GROQ_MODEL")
            or os.getenv("LLAMA_MODEL")
            or load_dotenv_value("LLAMA_MODEL")
            or DEFAULT_MODEL
        ),
        "llm_error": llm_error,
    }

    return extraction_result


def main() -> None:
    result = run_pipeline()
    output_file = OUTPUT_DIR / "hybrid_pa_pipeline_first_doc.json"
    output_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(str(output_file))


if __name__ == "__main__":
    main()
