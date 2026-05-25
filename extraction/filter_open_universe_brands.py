import csv
import json
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
INPUT_JSON = BASE_DIR / "output_test" / "raw_markdown_brand_file_map_open_universe.json"
INPUT_CSV = BASE_DIR / "output_test" / "raw_markdown_brand_file_map_open_universe.csv"
OUT_JSON = BASE_DIR / "output_test" / "raw_markdown_brand_file_map_open_universe_clean.json"
OUT_CSV = BASE_DIR / "output_test" / "raw_markdown_brand_file_map_open_universe_clean.csv"


NOISE_EXACT = {
    "AND",
    "OR",
    "ANY",
    "ALL",
    "ADD",
    "AIDS",
    "ADHD",
    "ALK",
    "ALK-POSITIVE",
    "AASLD-IDSA",
    "FDA",
    "PA",
    "PSA",
    "PUVA",
    "UVB",
    "MS",
    "RA",
    "UC",
    "CD",
    "AS",
    "NOMID",
    "SJIA",
    "PJIA",
    "GCA",
    "ERA",
    "BSA",
    "IV",
    "SC",
    "ACUTE",
    "ADULT",
    "ACCELERATED",
    "ADJUVANT",
    "AEDS",
    "ACID",
    "ACETATE",
    "ACETAT",
    "ABL1",
    "ABL-",
    "ALCL",
    "AML",
    "ANCA",
    "AQUEOUS",
    "AIDS-RELATED",
    "ABL-CLASS",
    "B-CELL TYPE",
    "CD30-POSITIVE",
    "G12C-POSITIVE",
    "GRADES 1-3",
    "GREATER THAN 50",
    "HGB 10G",
    "HGB 11G",
    "HGB 12G",
    "LENOX-GASTAUT",
    "LOWER-RISK",
    "MEDICALLY-ACCEPTED",
    "NODE-POSITIVE",
    "NON",
    "NON-CANCER PAIN",
    "NON-HIGH RISK MEDICATION",
    "NON-HODGKIN",
    "NON-METASTATIC",
    "NON-SMALL",
    "OFF",
    "OFF-LABEL",
    "ORAL-INTRANASAL",
}

NOISE_PATTERN = re.compile(
    r"\b(?:syndrome|disease|criteria|duration|restriction|policy|diagnosis|trial|response|contraindication|phase|treatment|request|member|patient|indication|guideline|association|society)\b",
    re.IGNORECASE,
)

GENERIC_SUFFIX_PATTERN = re.compile(
    r"(?:mab|nib|cept|zomib|ximab|tinib|sartan|pril|olol|azole|mycin|cycline|prazole|oxetine|triptyline)$",
    re.IGNORECASE,
)

ALLOWED_HYPHENATED_BRANDS = {
    "DEPO-TESTOSTERONE",
    "GAMUNEX-C",
    "PROLASTIN-C",
}


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def is_likely_drug_brand(brand: str, context: str, mention_count: int) -> bool:
    b = brand.strip()
    if not b:
        return False

    b_upper = b.upper()
    if b_upper in NOISE_EXACT:
        return False
    if "AASLD" in b_upper or "IDSA" in b_upper:
        return False

    # Hyphenated org/medical shorthand and too-short abbreviations are usually noise.
    if "-" in b and b_upper not in ALLOWED_HYPHENATED_BRANDS:
        if len(b) <= 20:
            return False
    if "-" in b and len(b) <= 12 and b_upper == b and b_upper not in ALLOWED_HYPHENATED_BRANDS:
        return False
    if len(b) <= 2:
        return False
    if re.fullmatch(r"[A-Z]{2,5}", b_upper):
        return False
    if re.search(r"\b(?:POSITIVE|RISK|GRADE|LOWER|GREATER|NON|OFF|LABEL)\b", b_upper):
        return False

    # Reject obvious non-brand medical/administrative strings.
    if NOISE_PATTERN.search(b):
        return False

    # Most drug brands are alphabetic-ish names; drop token soup.
    if re.search(r"\d{3,}", b):
        return False
    if re.search(r"[^A-Za-z0-9\s\-/]", b):
        return False

    # Generic molecule-like tokens are noise for this brand mapping step.
    if GENERIC_SUFFIX_PATTERN.search(b):
        return False

    # Positive context signals from flattened PA sections.
    c = context.lower()
    positive_context = any(
        key in c
        for key in [
            "prior authorization group",
            "drug names",
            "all fda",
            "requires prior authorization",
            "request is for",
        ]
    )

    # For open-universe mode we keep only candidates with strong PA table context.
    if not positive_context:
        return False

    return True


def main() -> None:
    if not INPUT_JSON.exists() or not INPUT_CSV.exists():
        raise FileNotFoundError("Open-universe input files are missing in output_test.")

    data = json.loads(INPUT_JSON.read_text(encoding="utf-8"))
    with INPUT_CSV.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    kept_rows = []
    removed_rows = []

    for row in rows:
        brand = row.get("brand_name", "").strip()
        context = row.get("sample_context", "")
        try:
            mention_count = int(row.get("mention_count", "0"))
        except ValueError:
            mention_count = 0

        if is_likely_drug_brand(brand, context, mention_count):
            kept_rows.append(row)
        else:
            removed_rows.append(row)

    # Stable sort for easier inspection.
    kept_rows.sort(key=lambda r: (r.get("source_file", ""), r.get("brand_name", "").lower()))

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["source_file", "brand_name", "mention_count", "sample_context"],
        )
        writer.writeheader()
        writer.writerows(kept_rows)

    per_file = {}
    for row in kept_rows:
        source = row["source_file"]
        per_file.setdefault(source, {"brands_found": [], "brand_mentions": {}})
        per_file[source]["brands_found"].append(row["brand_name"])
        per_file[source]["brand_mentions"][row["brand_name"]] = int(row["mention_count"])

    for source in per_file:
        per_file[source]["brands_found"] = sorted(set(per_file[source]["brands_found"]))
        per_file[source]["brand_count"] = len(per_file[source]["brands_found"])

    OUT_JSON.write_text(
        json.dumps(
            {
                "input_file_brand_rows": len(rows),
                "kept_file_brand_rows": len(kept_rows),
                "records": per_file,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"Input rows: {len(rows)}")
    print(f"Kept rows: {len(kept_rows)}")
    print(f"Removed rows: {len(removed_rows)}")
    print(f"Clean CSV: {OUT_CSV}")
    print(f"Clean JSON: {OUT_JSON}")


if __name__ == "__main__":
    main()
