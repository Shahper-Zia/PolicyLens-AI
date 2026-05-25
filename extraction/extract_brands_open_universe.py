import csv
import json
import re
from collections import Counter
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
RAW_MD_DIR = BASE_DIR / "data" / "extracted_pdfs" / "raw_markdown"
OUTPUT_TEST_DIR = BASE_DIR / "output_test"
OUTPUT_TEST_DIR.mkdir(parents=True, exist_ok=True)

CSV_OUT = OUTPUT_TEST_DIR / "raw_markdown_brand_file_map_open_universe.csv"
JSON_OUT = OUTPUT_TEST_DIR / "raw_markdown_brand_file_map_open_universe.json"


STOPWORDS = {
    "prior",
    "authorization",
    "group",
    "drug",
    "names",
    "plan",
    "year",
    "required",
    "medical",
    "information",
    "coverage",
    "duration",
    "age",
    "restrictions",
    "prescriber",
    "criteria",
    "policy",
    "approval",
    "initial",
    "continued",
    "therapy",
    "all",
    "fda",
    "indications",
}


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def is_plausible_brand(name: str) -> bool:
    name = name.strip(" ,;:.()[]{}")
    if len(name) < 3 or len(name) > 40:
        return False
    if not re.search(r"[A-Za-z]", name):
        return False
    low = name.lower()
    if low in STOPWORDS:
        return False
    if re.search(r"\b(?:month|months|years?|days?|mg|ml|uvb|puva)\b", low):
        return False
    return True


def title_case_brand(name: str) -> str:
    # Keep all-caps abbreviations when they are short; otherwise normalize visual consistency.
    if name.isupper() and len(name) <= 5:
        return name
    return " ".join(part.capitalize() if not part.isupper() else part for part in name.split())


def detect_from_parenthetical_lists(text: str) -> list[str]:
    candidates = []
    # Example: adalimumab (Humira), infliximab (Remicade)
    for match in re.finditer(r"\(([A-Za-z][A-Za-z0-9\s\-/&,]{1,80})\)", text):
        inside = match.group(1)
        for token in re.split(r",|/|\bor\b|\band\b", inside):
            token = token.strip()
            token = re.sub(r"\s+(?:®|™)$", "", token)
            token = re.sub(r"\s+", " ", token)
            if is_plausible_brand(token):
                candidates.append(token)
    return candidates


def detect_from_pa_group_blocks(text: str) -> list[str]:
    candidates = []
    lines = text.splitlines()

    for i, line in enumerate(lines):
        if "Prior Authorization Group" not in line and "Drug Names" not in line:
            continue

        window = " ".join(lines[i : min(len(lines), i + 8)])
        # Capture uppercase-ish tokens often flattened in PA tables.
        for token in re.findall(r"\b[A-Z][A-Z0-9\-]{2,}\b", window):
            if is_plausible_brand(token):
                candidates.append(token)

        # Capture title-case tokens in same table block.
        for token in re.findall(r"\b[A-Z][a-zA-Z0-9\-]{2,}\b", window):
            if is_plausible_brand(token):
                candidates.append(token)

    return candidates


def detect_from_drug_names_markdown_tables(text: str) -> list[str]:
    candidates = []
    for row in re.findall(r"^\|.*\|$", text, flags=re.MULTILINE):
        if "Drug Names" not in row and "Prior Authorization Group" not in row:
            continue
        for token in re.findall(r"\b[A-Z][A-Za-z0-9\-]{2,}\b", row):
            if is_plausible_brand(token):
                candidates.append(token)
    return candidates


def detect_brands(text: str) -> Counter:
    raw_candidates = []
    raw_candidates.extend(detect_from_parenthetical_lists(text))
    raw_candidates.extend(detect_from_pa_group_blocks(text))
    raw_candidates.extend(detect_from_drug_names_markdown_tables(text))

    counts = Counter()
    seen_norm_to_best = {}

    for name in raw_candidates:
        clean = re.sub(r"\s+(?:®|™)$", "", name).strip()
        clean = re.sub(r"\s+", " ", clean)
        if not is_plausible_brand(clean):
            continue

        norm = normalize(clean)
        if not norm:
            continue

        best = seen_norm_to_best.get(norm)
        if best is None or (clean.istitle() and not best.istitle()):
            seen_norm_to_best[norm] = clean
        counts[norm] += 1

    normalized_counts = Counter()
    for norm, count in counts.items():
        brand = title_case_brand(seen_norm_to_best[norm])
        normalized_counts[brand] += count
    return normalized_counts


def sample_context(text: str, brand: str) -> str:
    pattern = re.compile(rf"(?i)\b{re.escape(brand)}\b")
    m = pattern.search(text)
    if not m:
        return ""
    start = max(0, m.start() - 180)
    end = min(len(text), m.end() + 180)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def main() -> None:
    rows = []
    file_records = []
    for md_file in sorted(RAW_MD_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        brand_counts = detect_brands(text)

        brands_found = sorted(brand_counts.keys())
        mentions = {brand: int(brand_counts[brand]) for brand in brands_found}

        for brand in brands_found:
            rows.append(
                {
                    "source_file": md_file.name,
                    "brand_name": brand,
                    "mention_count": mentions[brand],
                    "sample_context": sample_context(text, brand),
                }
            )

        file_records.append(
            {
                "source_file": md_file.name,
                "brand_count": len(brands_found),
                "brands_found": brands_found,
                "brand_mentions": mentions,
            }
        )

    with CSV_OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["source_file", "brand_name", "mention_count", "sample_context"],
        )
        writer.writeheader()
        writer.writerows(rows)

    JSON_OUT.write_text(
        json.dumps(
            {
                "file_count": len(file_records),
                "file_brand_rows": len(rows),
                "records": file_records,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"Files scanned: {len(file_records)}")
    print(f"File-brand rows found: {len(rows)}")
    print(f"CSV: {CSV_OUT}")
    print(f"JSON: {JSON_OUT}")


if __name__ == "__main__":
    main()
