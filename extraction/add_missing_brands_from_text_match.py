import csv
import json
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
BRAND_CSV = BASE_DIR / "outputs" / "brand_names.csv"
COVERAGE_JSON = BASE_DIR / "outputs" / "brand_coverage_report.json"
TEXT_MATCH_JSON = BASE_DIR / "outputs" / "brands_in_pdf_text_match.json"


def normalize_brand(value: str) -> str:
    value = value.lower().strip()
    return re.sub(r"[^a-z0-9]+", "", value)


def split_brand_variants(value: str) -> list[str]:
    parts = re.split(r"\s*/\s*|\s+\band\b\s+", value, flags=re.IGNORECASE)
    return [part.strip() for part in parts if part.strip()]


def load_missing_brands() -> list[str]:
    data = json.loads(COVERAGE_JSON.read_text(encoding="utf-8"))
    return list(data.get("missing_brands", []))


def load_existing_keys(rows: list[dict]) -> set[tuple[str, str]]:
    keys = set()
    for row in rows:
        source_file = row.get("source_file", "").strip()
        for field in ("brand_name", "normalized_brand_name"):
            brand = row.get(field, "").strip()
            if brand:
                keys.add((normalize_brand(brand), source_file.lower()))
    return keys


def main() -> None:
    if not BRAND_CSV.exists():
        raise FileNotFoundError(f"Missing CSV: {BRAND_CSV}")
    if not COVERAGE_JSON.exists():
        raise FileNotFoundError(f"Missing coverage report: {COVERAGE_JSON}")
    if not TEXT_MATCH_JSON.exists():
        raise FileNotFoundError(f"Missing text match JSON: {TEXT_MATCH_JSON}")

    with BRAND_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    missing_brands = load_missing_brands()
    text_match = json.loads(TEXT_MATCH_JSON.read_text(encoding="utf-8"))
    existing_keys = load_existing_keys(rows)
    additions = []

    for target_brand in missing_brands:
        variants = split_brand_variants(target_brand)
        for file_stem, file_data in text_match.items():
            source_file = f"{file_stem}.md"
            brand_mentions = file_data.get("brand_mentions", {})
            brands_found = file_data.get("brands_found", [])

            found_lookup = {
                normalize_brand(brand): brand
                for brand in list(brands_found) + list(brand_mentions.keys())
            }

            for variant in variants:
                matched_brand = found_lookup.get(normalize_brand(variant))
                if not matched_brand:
                    continue

                row_key = (normalize_brand(matched_brand), source_file.lower())
                if row_key in existing_keys:
                    continue

                existing_keys.add(row_key)
                mentions = brand_mentions.get(matched_brand, "")
                additions.append(
                    {
                        "brand_name": matched_brand,
                        "normalized_brand_name": matched_brand,
                        "source_file": source_file,
                        "confidence": "text_match",
                        "evidence": f"brand_mentions={mentions}" if mentions != "" else "brands_found",
                        "notes": f"Added from {TEXT_MATCH_JSON.name}; target missing brand: {target_brand}",
                    }
                )

    if additions:
        rows.extend(additions)
        rows = sorted(rows, key=lambda row: (row.get("normalized_brand_name", "").lower(), row.get("source_file", "")))
        with BRAND_CSV.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    print(f"Missing targets checked: {len(missing_brands)}")
    print(f"Rows added to brand_names.csv: {len(additions)}")
    for row in additions:
        print(f"- {row['normalized_brand_name']} | {row['source_file']}")


if __name__ == "__main__":
    main()
