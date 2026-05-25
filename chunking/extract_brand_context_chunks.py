import csv
import json
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
RAW_MD_DIR = BASE_DIR / "data" / "extracted_pdfs" / "raw_markdown"
BRAND_CSV = BASE_DIR / "outputs" / "brand_names.csv"
OUTPUT_DIR = BASE_DIR / "outputs"
JSON_OUT = OUTPUT_DIR / "brand_context_chunks_full.json"
CSV_OUT = OUTPUT_DIR / "brand_context_chunks_full.csv"

MAX_CHUNK_CHARS = 9000
OVERLAP_LINES = 8
NEIGHBOR_WINDOW = 1

SECTION_START_PATTERNS = [
    re.compile(r"^\s{0,3}#{1,6}\s+"),
    re.compile(r"\bPrior Authorization Group\b", re.IGNORECASE),
]


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def text_contains_brand(text: str, brand: str) -> bool:
    n_brand = normalize_text(brand)
    return bool(n_brand) and n_brand in normalize_text(text)


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


def build_chunk(source_file: str, chunk_index: int, start: int, end: int, lines: list[str], heading: str) -> dict:
    return {
        "chunk_id": f"{Path(source_file).stem}::chunk_{chunk_index:04d}",
        "source_file": source_file,
        "chunk_index": chunk_index,
        "start_line": start + 1,
        "end_line": end,
        "heading": heading,
        "text": "\n".join(lines).strip(),
    }


def split_long_segment(lines: list[str], source_file: str, seg_start: int, seg_end: int, chunk_start_idx: int) -> list[dict]:
    chunks = []
    chunk_idx = chunk_start_idx
    current_start = seg_start

    while current_start < seg_end:
        current_lines = []
        current_len = 0
        idx = current_start
        while idx < seg_end:
            line_len = len(lines[idx]) + 1
            if current_lines and current_len + line_len > MAX_CHUNK_CHARS:
                break
            current_lines.append(lines[idx])
            current_len += line_len
            idx += 1

        if not current_lines:
            break

        chunks.append(
            build_chunk(source_file, chunk_idx, current_start, idx, current_lines, heading_before(lines, current_start))
        )
        chunk_idx += 1

        if idx >= seg_end:
            break
        current_start = max(idx - OVERLAP_LINES, current_start + 1)

    return chunks


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
        chunks.extend(split_long_segment(lines, source_file, start, next_start, len(chunks) + 1))
    return chunks


def retrieve_chunks_for_brand(chunks: list[dict], aliases: list[str]) -> list[dict]:
    matched = set()
    reasons = {}
    alias_set = {a.strip() for a in aliases if a and a.strip()}

    for i, chunk in enumerate(chunks):
        for alias in alias_set:
            if text_contains_brand(chunk["text"], alias):
                matched.add(i)
                reasons.setdefault(i, set()).add(f"matched:{alias}")

    selected = set(matched)
    for i in matched:
        for n in range(i - NEIGHBOR_WINDOW, i + NEIGHBOR_WINDOW + 1):
            if 0 <= n < len(chunks):
                selected.add(n)
                if n != i:
                    reasons.setdefault(n, set()).add("nearby_context")

    out = []
    for i in sorted(selected):
        item = dict(chunks[i])
        item["match_type"] = ";".join(sorted(reasons.get(i, {"section_context"})))
        out.append(item)
    return out


def main() -> None:
    rows = list(csv.DictReader(BRAND_CSV.open(newline="", encoding="utf-8")))
    md_cache = {}
    chunk_cache = {}
    results = []
    missing_files = []

    for idx, row in enumerate(rows, start=1):
        brand_name = (row.get("brand_name") or "").strip()
        normalized_brand_name = (row.get("normalized_brand_name") or "").strip()
        source_file = (row.get("source_file") or "").strip()

        if not source_file or not brand_name:
            continue

        md_path = RAW_MD_DIR / source_file
        if not md_path.exists():
            missing_files.append({"row_number": idx, "brand_name": brand_name, "source_file": source_file})
            continue

        if source_file not in md_cache:
            md_cache[source_file] = md_path.read_text(encoding="utf-8", errors="ignore")
            chunk_cache[source_file] = chunk_markdown(source_file, md_cache[source_file])

        aliases = [brand_name, normalized_brand_name]
        brand_chunks = retrieve_chunks_for_brand(chunk_cache[source_file], aliases)
        for c in brand_chunks:
            results.append(
                {
                    "row_number": idx,
                    "brand_name": brand_name,
                    "normalized_brand_name": normalized_brand_name,
                    "source_file": source_file,
                    "chunk_id": c["chunk_id"],
                    "chunk_index": c["chunk_index"],
                    "start_line": c["start_line"],
                    "end_line": c["end_line"],
                    "heading": c["heading"],
                    "match_type": c["match_type"],
                    "chunk_text": c["text"],
                }
            )

    summary = {
        "input_rows": len(rows),
        "output_rows": len(results),
        "missing_markdown_rows": len(missing_files),
        "missing_markdown_details": missing_files,
    }

    JSON_OUT.write_text(json.dumps({"summary": summary, "rows": results}, ensure_ascii=False, indent=2), encoding="utf-8")

    with CSV_OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "row_number",
                "brand_name",
                "normalized_brand_name",
                "source_file",
                "chunk_id",
                "chunk_index",
                "start_line",
                "end_line",
                "heading",
                "match_type",
                "chunk_text",
            ],
        )
        writer.writeheader()
        writer.writerows(results)

    print(f"Processed rows: {len(rows)}")
    print(f"Extracted chunk rows: {len(results)}")
    print(f"Missing markdown rows: {len(missing_files)}")
    print(f"JSON output: {JSON_OUT}")
    print(f"CSV output: {CSV_OUT}")


if __name__ == "__main__":
    main()
