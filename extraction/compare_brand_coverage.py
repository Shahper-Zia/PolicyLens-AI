import csv
import json
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
BRAND_CSV = BASE_DIR / "outputs" / "brand_names.csv"
REPORT_CSV = BASE_DIR / "outputs" / "brand_coverage_report.csv"
REPORT_JSON = BASE_DIR / "outputs" / "brand_coverage_report.json"


TARGET_BRANDS = [
    "Acitretin",
    "Amjevita",
    "Avsola",
    "Bimzelx",
    "Cimzia",
    "Cosentyx",
    "Cyclosporine",
    "Cyltezo",
    "Enbrel",
    "Hulio",
    "Humira",
    "Hyrimoz",
    "Idacio",
    "Ilumya",
    "Inflectra",
    "Methotrexate",
    "Otezla",
    "Otulfi",
    "Psychiva / Quallent",
    "Remicade",
    "Renflexis",
    "Selarsdi",
    "Siliq",
    "Skyrizi",
    "Sotyktu",
    "Stelara",
    "Steqeyma",
    "Taltz",
    "Tremfya",
    "Vtama",
    "Wezlana",
    "Yesintek",
    "Yuflyma",
    "Yusimry",
    "Zoryve",
    "Pyzchiva",
    "Imuldosa",
    "Quallent",
]


def normalize_brand(value: str) -> str:
    value = value.lower().strip()
    value = value.replace("&", "and")
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


def split_brand_variants(value: str) -> list[str]:
    parts = re.split(r"\s*/\s*|\s+\band\b\s+", value, flags=re.IGNORECASE)
    return [part.strip() for part in parts if part.strip()]


def load_extracted_rows() -> list[dict]:
    with BRAND_CSV.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_extracted_index(rows: list[dict]) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for row in rows:
        names = {
            row.get("brand_name", ""),
            row.get("normalized_brand_name", ""),
        }
        for name in names:
            name = name.strip()
            if not name:
                continue
            index.setdefault(normalize_brand(name), []).append(row)
    return index


def main() -> None:
    if not BRAND_CSV.exists():
        raise FileNotFoundError(f"Missing input CSV: {BRAND_CSV}")

    rows = load_extracted_rows()
    extracted_index = build_extracted_index(rows)
    report_rows = []

    for target in TARGET_BRANDS:
        variants = split_brand_variants(target)
        matched_rows = []
        matched_names = []

        for variant in variants:
            matches = extracted_index.get(normalize_brand(variant), [])
            if matches:
                matched_names.append(variant)
                matched_rows.extend(matches)

        unique_sources = sorted(
            {
                row.get("source_file", "")
                for row in matched_rows
                if row.get("source_file", "")
            }
        )

        report_rows.append(
            {
                "target_brand": target,
                "status": "present" if matched_rows else "missing",
                "matched_variants": "; ".join(sorted(set(matched_names))),
                "matched_count": len(matched_rows),
                "source_files": "; ".join(unique_sources),
            }
        )

    with REPORT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "target_brand",
                "status",
                "matched_variants",
                "matched_count",
                "source_files",
            ],
        )
        writer.writeheader()
        writer.writerows(report_rows)

    summary = {
        "input_csv": str(BRAND_CSV),
        "target_count": len(TARGET_BRANDS),
        "present_count": sum(1 for row in report_rows if row["status"] == "present"),
        "missing_count": sum(1 for row in report_rows if row["status"] == "missing"),
        "missing_brands": [
            row["target_brand"] for row in report_rows if row["status"] == "missing"
        ],
        "rows": report_rows,
    }
    REPORT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Present: {summary['present_count']} / {summary['target_count']}")
    print(f"Missing: {summary['missing_count']}")
    print(f"CSV report: {REPORT_CSV}")
    print(f"JSON report: {REPORT_JSON}")
    if summary["missing_brands"]:
        print("Missing brands:")
        for brand in summary["missing_brands"]:
            print(f"- {brand}")


if __name__ == "__main__":
    main()
