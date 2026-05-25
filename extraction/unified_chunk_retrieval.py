import csv
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import fitz
import pdfplumber
from sklearn.feature_extraction.text import TfidfVectorizer

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


BASE_DIR = Path(__file__).resolve().parents[1]
SUBMISSIONS_CSV = BASE_DIR / "submissions.csv"
RAW_MARKDOWN_DIR = BASE_DIR / "data" / "extracted_pdfs" / "raw_markdown"
RAW_PDF_DIR = BASE_DIR / "data" / "raw_pdfs"
OUTPUT_DIR = BASE_DIR / "output_test"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class UnifiedChunk:
    filename: str
    brand_name: str
    chunk_id: str
    source_type: str
    section_title: str
    page_number: int | None
    text: str
    heading_path: list[str]
    quality_flags: list[str]
    metadata: dict[str, Any]


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


def parse_markdown_pages(markdown_text: str) -> list[tuple[int | None, str]]:
    pattern = re.compile(r"(?m)^Page:\s*$\s*^(?P<num>\d+)\s+of\s+\d+\s*$")
    matches = list(pattern.finditer(markdown_text))
    if not matches:
        return [(None, markdown_text)]

    pages: list[tuple[int | None, str]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(markdown_text)
        pages.append((int(match.group("num")), markdown_text[start:end].strip()))
    return pages


def detect_quality_flags(text: str, source_type: str) -> list[str]:
    flags: list[str] = []
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return ["empty"]

    if source_type == "table":
        flags.append("table_source")
    if "â" in text or "�" in text:
        flags.append("encoding_artifacts")
    if sum(1 for line in lines if line.strip().startswith("|")) >= 2:
        flags.append("markdown_table")
    if sum(1 for line in lines if line.strip().startswith("-")) >= 8 and len(lines) >= 10:
        flags.append("dense_list_or_flattened_table")
    if sum(1 for line in lines if len(line.strip()) <= 3) >= 4:
        flags.append("fragmented_lines")
    if any(term in text.lower() for term in ("quantity level limit", "dosage and administration", "approval duration")):
        flags.append("high_value_layout_section")
    return flags


def chunk_markdown(markdown_text: str, filename: str, brand_name: str) -> list[UnifiedChunk]:
    pages = parse_markdown_pages(markdown_text)
    chunks: list[UnifiedChunk] = []
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
            flags = detect_quality_flags(text, "docling_md")
            chunks.append(
                UnifiedChunk(
                    filename=filename,
                    brand_name=brand_name,
                    chunk_id=f"md_{chunk_counter}",
                    source_type="docling_md",
                    section_title=current_heading,
                    page_number=page_number,
                    text=text,
                    heading_path=list(heading_path),
                    quality_flags=flags,
                    metadata={"source": "docling_markdown"},
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
                if block_lines:
                    flush_block()
                continue

            block_lines.append(line)

        flush_block()

    return chunks


def extract_pdf_text_chunks(pdf_path: Path, filename: str, brand_name: str) -> list[UnifiedChunk]:
    chunks: list[UnifiedChunk] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            text = normalize_whitespace(page.extract_text(layout=True) or "")
            if not text:
                continue
            chunks.append(
                UnifiedChunk(
                    filename=filename,
                    brand_name=brand_name,
                    chunk_id=f"pdftext_{page_index}",
                    source_type="pdfplumber_text",
                    section_title=f"PDF Page {page_index}",
                    page_number=page_index,
                    text=text,
                    heading_path=[f"PDF Page {page_index}"],
                    quality_flags=detect_quality_flags(text, "pdfplumber_text"),
                    metadata={"extraction": "pdfplumber", "layout": True},
                )
            )
    return chunks


def extract_table_chunks(pdf_path: Path, filename: str, brand_name: str) -> list[UnifiedChunk]:
    chunks: list[UnifiedChunk] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables() or []
            for table_index, table in enumerate(tables, start=1):
                rows: list[list[str]] = []
                for row in table:
                    if not row:
                        continue
                    cleaned = [normalize_whitespace(cell or "") for cell in row]
                    if any(cleaned):
                        rows.append(cleaned)
                if not rows:
                    continue
                table_text = "\n".join(" | ".join(row) for row in rows)
                chunks.append(
                    UnifiedChunk(
                        filename=filename,
                        brand_name=brand_name,
                        chunk_id=f"table_{page_index}_{table_index}",
                        source_type="table",
                        section_title=f"Page {page_index} Table {table_index}",
                        page_number=page_index,
                        text=table_text,
                        heading_path=[f"Page {page_index}", f"Table {table_index}"],
                        quality_flags=detect_quality_flags(table_text, "table"),
                        metadata={"rows": rows, "source": "pdfplumber_table"},
                    )
                )
    return chunks


def extract_fitz_fallback_chunks(pdf_path: Path, filename: str, brand_name: str, page_numbers: list[int] | None = None) -> list[UnifiedChunk]:
    chunks: list[UnifiedChunk] = []
    doc = fitz.open(pdf_path)
    try:
        target_pages = page_numbers or list(range(1, doc.page_count + 1))
        for page_number in target_pages:
            if page_number < 1 or page_number > doc.page_count:
                continue
            page = doc.load_page(page_number - 1)
            text = normalize_whitespace(page.get_text("text") or "")
            if not text:
                continue
            chunks.append(
                UnifiedChunk(
                    filename=filename,
                    brand_name=brand_name,
                    chunk_id=f"fitz_{page_number}",
                    source_type="fitz_fallback",
                    section_title=f"Fitz Page {page_number}",
                    page_number=page_number,
                    text=text,
                    heading_path=[f"Fitz Page {page_number}"],
                    quality_flags=detect_quality_flags(text, "fitz_fallback"),
                    metadata={"extraction": "fitz", "source": "fallback"},
                )
            )
    finally:
        doc.close()
    return chunks


def build_unified_chunks(filename: str, brand_name: str, markdown_path: Path, pdf_path: Path) -> list[UnifiedChunk]:
    markdown_text = markdown_path.read_text(encoding="utf-8", errors="ignore")
    markdown_chunks = chunk_markdown(markdown_text, filename, brand_name)
    pdf_text_chunks = extract_pdf_text_chunks(pdf_path, filename, brand_name)
    table_chunks = extract_table_chunks(pdf_path, filename, brand_name)

    combined = markdown_chunks + pdf_text_chunks + table_chunks
    if not pdf_text_chunks:
        combined.extend(extract_fitz_fallback_chunks(pdf_path, filename, brand_name))

    return combined


def keyword_score(text: str, query: str) -> float:
    text_l = text.lower()
    tokens = [token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 2]
    if not tokens:
        return 0.0
    hits = sum(1 for token in tokens if token in text_l)
    return hits / len(tokens)


def build_retrieval_index(chunks: list[UnifiedChunk], query: str, top_k: int = 10) -> list[dict[str, Any]]:
    texts = [chunk.text for chunk in chunks]
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(texts + [query])
    chunk_matrix = matrix[: len(chunks)]
    query_vec = matrix[len(chunks)]
    semantic_scores = (chunk_matrix @ query_vec.T).toarray().ravel()

    ranked: list[tuple[float, int, float, float]] = []
    for idx, chunk in enumerate(chunks):
        semantic = float(semantic_scores[idx])
        keyword = keyword_score(chunk.text, query)
        table_boost = 0.15 if chunk.source_type == "table" else 0.0
        score = semantic + keyword + table_boost
        ranked.append((score, idx, semantic, keyword))

    ranked.sort(reverse=True)
    return [
        {
            "chunk_id": chunks[idx].chunk_id,
            "source_type": chunks[idx].source_type,
            "section_title": chunks[idx].section_title,
            "page_number": chunks[idx].page_number,
            "score": round(score, 4),
            "semantic_score": round(semantic, 4),
            "keyword_score": round(keyword, 4),
        }
        for score, idx, semantic, keyword in ranked[:top_k]
    ]


def build_parameter_queries(brand_name: str) -> dict[str, str]:
    return {
        "Age": f"{brand_name} age eligibility or age restrictions prior authorization",
        "Step Therapy Requirements Documented in Policy": f"{brand_name} step therapy preferred products prior authorization",
        "Number of Steps through Brands": f"{brand_name} branded biologic step therapy preferred products",
        "Number of Steps through Generic": f"{brand_name} generic non-biologic step therapy topicals",
        "Step through-Phototherapy": f"{brand_name} phototherapy PUVA UVB prior authorization",
        "TB Test required": f"{brand_name} tuberculosis TB test screening prior authorization",
        "Initial Authorization Duration(in-months)": f"{brand_name} initial authorization duration months",
        "Reauthorization Duration(in-months)": f"{brand_name} reauthorization duration months",
        "Reauthorization Required": f"{brand_name} renewal reauthorization required",
        "Reauthorization Requirements Documented in Policy": f"{brand_name} continuation of therapy reauthorization criteria",
        "Specialist Types": f"{brand_name} prescriber specialty specialist types",
        "Quantity Limits": f"{brand_name} quantity limit dosing limit quantity level limit",
    }


def main() -> None:
    first_row = load_first_submission()
    filename = first_row["Filename"]
    brand_name = first_row["Brand"]
    markdown_path, pdf_path = locate_input_files(filename)

    chunks = build_unified_chunks(filename, brand_name, markdown_path, pdf_path)
    parameter_queries = build_parameter_queries(brand_name)

    retrieval_bundle = {
        "filename": filename,
        "brand_name": brand_name,
        "chunk_count": len(chunks),
        "source_counts": {
            "docling_md": sum(1 for chunk in chunks if chunk.source_type == "docling_md"),
            "pdfplumber_text": sum(1 for chunk in chunks if chunk.source_type == "pdfplumber_text"),
            "table": sum(1 for chunk in chunks if chunk.source_type == "table"),
            "fitz_fallback": sum(1 for chunk in chunks if chunk.source_type == "fitz_fallback"),
        },
        "parameter_queries": parameter_queries,
        "retrieval": {
            parameter: build_retrieval_index(chunks, query, top_k=6)
            for parameter, query in parameter_queries.items()
        },
        "chunks": [asdict(chunk) for chunk in chunks],
    }

    output_file = OUTPUT_DIR / "unified_chunk_retrieval_first_doc.json"
    output_file.write_text(json.dumps(retrieval_bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    print(str(output_file))


if __name__ == "__main__":
    main()
