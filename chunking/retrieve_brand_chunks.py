import csv
import json
import re
from collections import defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
RAW_MD_DIR = BASE_DIR / "data" / "extracted_pdfs" / "raw_markdown"
BRAND_CSV = BASE_DIR / "outputs" / "brand_names.csv"
OUTPUT_DIR = BASE_DIR / "outputs"
JSON_OUT = OUTPUT_DIR / "brand_relevant_chunks.json"
CSV_OUT = OUTPUT_DIR / "brand_relevant_chunks.csv"

MAX_CHUNK_CHARS = 9000
OVERLAP_LINES = 8
NEIGHBOR_WINDOW = 1
INCLUDE_UNIVERSAL_CHUNKS = False

SECTION_START_PATTERNS = [
    re.compile(r"^\s{0,3}#{1,6}\s+"),
    re.compile(r"\bPrior Authorization Group\b", re.IGNORECASE),
]

UNIVERSAL_KEYWORDS = [
    "policy/criteria",
    "initial approval criteria",
    "continued therapy",
    "continuation",
    "reauthorization",
    "renewal",
    "approval duration",
    "quantity limit",
    "quantity limits",
    "dosage and administration",
    "general information",
    "appendix",
    "other criteria",
]


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def text_contains_brand(text: str, brand: str) -> bool:
    normalized_brand = normalize_text(brand)
    if not normalized_brand:
        return False
    return normalized_brand in normalize_text(text)


def read_brand_file_map() -> dict[str, dict[str, set[str]]]:
    brand_file_map: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    with BRAND_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            source_file = row.get("source_file", "").strip()
            if not source_file:
                continue

            normalized_brand = row.get("normalized_brand_name", "").strip()
            brand_name = row.get("brand_name", "").strip()
            canonical = normalized_brand or brand_name
            if not canonical:
                continue

            brand_file_map[source_file][canonical].update(
                brand for brand in [normalized_brand, brand_name] if brand
            )

    return brand_file_map


def is_section_start(line: str) -> bool:
    return any(pattern.search(line) for pattern in SECTION_START_PATTERNS)


def is_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def heading_before(lines: list[str], start: int) -> str:
    for idx in range(start, -1, -1):
        line = lines[idx].strip()
        if re.match(r"^#{1,6}\s+", line):
            return line
    return ""


def split_long_segment(
    lines: list[str],
    source_file: str,
    segment_start: int,
    segment_end: int,
    chunk_start_index: int,
) -> list[dict]:
    chunks = []
    chunk_index = chunk_start_index
    current_start = segment_start

    while current_start < segment_end:
        current_lines: list[str] = []
        current_len = 0
        idx = current_start

        while idx < segment_end:
            line_len = len(lines[idx]) + 1
            if current_lines and current_len + line_len > MAX_CHUNK_CHARS:
                break

            current_lines.append(lines[idx])
            current_len += line_len
            idx += 1

        if not current_lines:
            break

        chunks.append(
            build_chunk(
                source_file,
                chunk_index,
                current_start,
                idx,
                current_lines,
                heading_before(lines, current_start),
            )
        )
        chunk_index += 1

        if idx >= segment_end:
            break

        next_start = max(idx - OVERLAP_LINES, current_start + 1)
        current_start = next_start

    return chunks


def build_chunk(
    source_file: str,
    chunk_index: int,
    start_line: int,
    end_line: int,
    lines: list[str],
    heading: str,
) -> dict:
    return {
        "chunk_id": f"{Path(source_file).stem}::chunk_{chunk_index:04d}",
        "source_file": source_file,
        "chunk_index": chunk_index,
        "start_line": start_line + 1,
        "end_line": end_line,
        "heading": heading,
        "text": "\n".join(lines).strip(),
    }


def chunk_markdown(source_file: str, text: str) -> list[dict]:
    lines = text.splitlines()
    if not lines:
        return []

    starts = {0}
    in_table = False

    for idx, line in enumerate(lines):
        table_line = is_table_line(line)
        if table_line:
            if not in_table:
                starts.add(idx)
            in_table = True
            continue

        if in_table:
            starts.add(idx)
            in_table = False

        if is_section_start(line):
            starts.add(idx)

    ordered_starts = sorted(starts)
    chunks = []

    for start, next_start in zip(ordered_starts, ordered_starts[1:] + [len(lines)]):
        if start >= next_start:
            continue
        segment_chunks = split_long_segment(
            lines,
            source_file,
            start,
            next_start,
            len(chunks) + 1,
        )
        chunks.extend(segment_chunks)

    return chunks


def is_universal_chunk(chunk: dict) -> bool:
    text = f"{chunk.get('heading', '')}\n{chunk.get('text', '')}".lower()
    return any(keyword in text for keyword in UNIVERSAL_KEYWORDS)


def retrieve_chunks_for_brand(
    chunks: list[dict],
    brand: str,
    aliases: set[str],
) -> list[dict]:
    matched_indexes = set()
    reasons_by_index: dict[int, set[str]] = defaultdict(set)

    for idx, chunk in enumerate(chunks):
        chunk_text = chunk["text"]
        for alias in aliases | {brand}:
            if text_contains_brand(chunk_text, alias):
                matched_indexes.add(idx)
                reasons_by_index[idx].add("brand_exact")
                reasons_by_index[idx].add(f"matched:{alias}")

    selected_indexes = set(matched_indexes)
    for idx in matched_indexes:
        for neighbor in range(idx - NEIGHBOR_WINDOW, idx + NEIGHBOR_WINDOW + 1):
            if 0 <= neighbor < len(chunks):
                selected_indexes.add(neighbor)
                if neighbor != idx:
                    reasons_by_index[neighbor].add("nearby_context")

    if INCLUDE_UNIVERSAL_CHUNKS:
        for idx, chunk in enumerate(chunks):
            if is_universal_chunk(chunk):
                selected_indexes.add(idx)
                reasons_by_index[idx].add("universal_criteria")

    results = []
    for idx in sorted(selected_indexes):
        chunk = dict(chunks[idx])
        chunk["brand"] = brand
        chunk["match_type"] = ";".join(sorted(reasons_by_index[idx])) or "section_context"
        results.append(chunk)

    return results


def main() -> None:
    brand_file_map = read_brand_file_map()
    all_results = []
    summary = {
        "source_brand_file_count": sum(len(brands) for brands in brand_file_map.values()),
        "files": {},
    }

    for source_file, brand_map in sorted(brand_file_map.items()):
        markdown_path = RAW_MD_DIR / source_file
        if not markdown_path.exists():
            summary["files"][source_file] = {
                "status": "missing_markdown",
                "brand_count": len(brand_map),
                "retrieved_chunk_count": 0,
            }
            continue

        text = markdown_path.read_text(encoding="utf-8", errors="ignore")
        chunks = chunk_markdown(source_file, text)
        file_result_count = 0

        for brand, aliases in sorted(brand_map.items()):
            brand_results = retrieve_chunks_for_brand(chunks, brand, aliases)
            file_result_count += len(brand_results)
            all_results.extend(brand_results)

        summary["files"][source_file] = {
            "status": "ok",
            "brand_count": len(brand_map),
            "document_chunk_count": len(chunks),
            "retrieved_chunk_count": file_result_count,
        }

    JSON_OUT.write_text(
        json.dumps(
            {
                "summary": summary,
                "chunks": all_results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with CSV_OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "source_file",
                "brand",
                "chunk_id",
                "chunk_index",
                "start_line",
                "end_line",
                "heading",
                "match_type",
                "text_preview",
            ],
        )
        writer.writeheader()
        for row in all_results:
            writer.writerow(
                {
                    "source_file": row["source_file"],
                    "brand": row["brand"],
                    "chunk_id": row["chunk_id"],
                    "chunk_index": row["chunk_index"],
                    "start_line": row["start_line"],
                    "end_line": row["end_line"],
                    "heading": row["heading"],
                    "match_type": row["match_type"],
                    "text_preview": row["text"][:500].replace("\n", " "),
                }
            )

    print(f"Brand-file pairs: {summary['source_brand_file_count']}")
    print(f"Retrieved rows: {len(all_results)}")
    print(f"JSON: {JSON_OUT}")
    print(f"CSV: {CSV_OUT}")


if __name__ == "__main__":
    main()
