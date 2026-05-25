import csv
import json
import os
import re
import time
from pathlib import Path

from google import genai


BASE_DIR = Path(__file__).resolve().parents[1]
RAW_MD_DIR = BASE_DIR / "data" / "extracted_pdfs" / "raw_markdown"
BRAND_CSV = BASE_DIR / "outputs" / "brand_names.csv"
ENV_FILE = BASE_DIR / ".env"
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

JSON_OUT = OUTPUT_DIR / "brand_context_chunks_llm_filtered.json"
CSV_OUT = OUTPUT_DIR / "brand_context_chunks_llm_filtered.csv"

MAX_CHUNK_CHARS = 9000
OVERLAP_LINES = 8
NEIGHBOR_WINDOW = 1
REQUEST_DELAY_SECONDS = 0.25

SECTION_START_PATTERNS = [
    re.compile(r"^\s{0,3}#{1,6}\s+"),
    re.compile(r"\bPrior Authorization Group\b", re.IGNORECASE),
]


def load_dotenv_value(key: str) -> str:
    if not ENV_FILE.exists():
        return ""
    for line in ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return ""


GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or load_dotenv_value("GEMINI_API_KEY")).strip()
GEMINI_MODEL = (os.getenv("GEMINI_MODEL") or load_dotenv_value("GEMINI_MODEL") or "gemini-2.5-flash").strip()


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def text_contains_brand(text: str, brand: str) -> bool:
    n_brand = normalize_text(brand)
    return bool(n_brand) and n_brand in normalize_text(text)


def is_section_start(line: str) -> bool:
    return any(pattern.search(line) for pattern in SECTION_START_PATTERNS)


def is_table_line(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|")


def heading_before(lines: list[str], start: int) -> str:
    for idx in range(start, -1, -1):
        if re.match(r"^#{1,6}\s+", lines[idx].strip()):
            return lines[idx].strip()
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
    out = []
    chunk_idx = chunk_start_idx
    current_start = seg_start
    while current_start < seg_end:
        current_lines = []
        current_len = 0
        idx = current_start
        while idx < seg_end:
            l = len(lines[idx]) + 1
            if current_lines and current_len + l > MAX_CHUNK_CHARS:
                break
            current_lines.append(lines[idx])
            current_len += l
            idx += 1
        if not current_lines:
            break
        out.append(build_chunk(source_file, chunk_idx, current_start, idx, current_lines, heading_before(lines, current_start)))
        chunk_idx += 1
        if idx >= seg_end:
            break
        current_start = max(idx - OVERLAP_LINES, current_start + 1)
    return out


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
    ordered = sorted(starts)
    chunks = []
    for start, nxt in zip(ordered, ordered[1:] + [len(lines)]):
        if start >= nxt:
            continue
        chunks.extend(split_long_segment(lines, source_file, start, nxt, len(chunks) + 1))
    return chunks


def candidate_chunks_for_brand(chunks: list[dict], aliases: list[str]) -> list[dict]:
    alias_set = {a.strip() for a in aliases if a and a.strip()}
    matched = set()
    for i, c in enumerate(chunks):
        for alias in alias_set:
            if text_contains_brand(c["text"], alias):
                matched.add(i)
                break
    selected = set(matched)
    for i in matched:
        for n in range(i - NEIGHBOR_WINDOW, i + NEIGHBOR_WINDOW + 1):
            if 0 <= n < len(chunks):
                selected.add(n)
    return [chunks[i] for i in sorted(selected)]


def parse_json_object(text: str) -> dict:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def llm_classify_chunk(client: genai.Client, brand_name: str, alias_list: list[str], chunk: dict) -> dict:
    prompt = f"""
You are classifying a policy markdown chunk for whether it is truly about a target brand.

Target brand: {brand_name}
Aliases: {", ".join(alias_list) if alias_list else brand_name}

Return STRICT JSON object only with keys:
- label: one of ["primary_brand_context", "secondary_mention", "multi_brand_shared", "irrelevant"]
- keep: boolean
- confidence: number from 0 to 1
- rationale: short string

Rules:
- primary_brand_context: chunk is mainly criteria/coverage/details for target brand.
- secondary_mention: target brand appears as prerequisite/comparator/history for another main product.
- multi_brand_shared: criteria section genuinely shared across multiple listed brands.
- irrelevant: not useful for extracting target brand criteria.
- keep=true only for primary_brand_context OR multi_brand_shared with strong relevance.

Chunk heading: {chunk.get("heading", "")}
Chunk text:
{chunk.get("text", "")}
""".strip()
    resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    parsed = parse_json_object(resp.text or "")
    label = parsed.get("label", "irrelevant")
    keep = bool(parsed.get("keep", False))
    confidence = parsed.get("confidence", 0)
    rationale = parsed.get("rationale", "")
    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0.0
    if label not in {"primary_brand_context", "secondary_mention", "multi_brand_shared", "irrelevant"}:
        label = "irrelevant"
    return {"label": label, "keep": keep, "confidence": confidence, "rationale": str(rationale)}


def main() -> None:
    if not GEMINI_API_KEY:
        raise RuntimeError("Missing GEMINI_API_KEY (env or .env)")
    client = genai.Client(api_key=GEMINI_API_KEY)

    rows = list(csv.DictReader(BRAND_CSV.open(newline="", encoding="utf-8")))
    md_cache = {}
    chunk_cache = {}
    results = []

    for idx, row in enumerate(rows, start=1):
        brand_name = (row.get("brand_name") or "").strip()
        normalized_brand_name = (row.get("normalized_brand_name") or "").strip()
        source_file = (row.get("source_file") or "").strip()
        if not source_file or not brand_name:
            continue
        md_path = RAW_MD_DIR / source_file
        if not md_path.exists():
            continue
        if source_file not in md_cache:
            md_cache[source_file] = md_path.read_text(encoding="utf-8", errors="ignore")
            chunk_cache[source_file] = chunk_markdown(source_file, md_cache[source_file])

        aliases = [brand_name, normalized_brand_name]
        candidates = candidate_chunks_for_brand(chunk_cache[source_file], aliases)
        for chunk in candidates:
            cls = llm_classify_chunk(client, brand_name, aliases, chunk)
            time.sleep(REQUEST_DELAY_SECONDS)
            if not cls["keep"]:
                continue
            results.append(
                {
                    "row_number": idx,
                    "brand_name": brand_name,
                    "normalized_brand_name": normalized_brand_name,
                    "source_file": source_file,
                    "chunk_id": chunk["chunk_id"],
                    "chunk_index": chunk["chunk_index"],
                    "start_line": chunk["start_line"],
                    "end_line": chunk["end_line"],
                    "heading": chunk["heading"],
                    "llm_label": cls["label"],
                    "llm_confidence": cls["confidence"],
                    "llm_rationale": cls["rationale"],
                    "chunk_text": chunk["text"],
                }
            )

    summary = {"input_rows": len(rows), "kept_rows": len(results), "model": GEMINI_MODEL}
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
                "llm_label",
                "llm_confidence",
                "llm_rationale",
                "chunk_text",
            ],
        )
        writer.writeheader()
        writer.writerows(results)
    print(f"Input rows: {len(rows)}")
    print(f"Kept rows: {len(results)}")
    print(f"JSON output: {JSON_OUT}")
    print(f"CSV output: {CSV_OUT}")


if __name__ == "__main__":
    main()
