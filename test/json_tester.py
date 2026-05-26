import json
from pathlib import Path
from typing import Any


def _extract_filename_and_values(payload: dict[str, Any], json_stem: str) -> tuple[str, list[str]]:
    if "file_name" in payload and "brands" in payload:
        file_name = str(payload["file_name"])
        raw_values = payload.get("brands", [])
    else:
        key_candidates = [k for k, v in payload.items() if isinstance(v, list)]
        if not key_candidates:
            return f"{json_stem}.md", []
        file_name = key_candidates[0]
        raw_values = payload.get(file_name, [])

    values = [str(v).strip() for v in raw_values if str(v).strip()]
    return file_name, values


def run_json_text_search_validation(
    json_dir: str | Path = "data/brand_file_univ",
    text_dir: str | Path = "data/extracted_pdfs_mds",
    report_output_path: str | Path = "data/brand_file_univ/json_validation_report.json",
) -> dict[str, Any]:
    json_path = Path(json_dir)
    text_path = Path(text_dir)

    total_json = 0
    total_terms = 0
    matched_terms = 0
    report: dict[str, Any] = {}

    for json_file in sorted(json_path.glob("*.json")):
        total_json += 1
        payload = json.loads(json_file.read_text(encoding="utf-8"))
        file_name, expected_values = _extract_filename_and_values(payload, json_file.stem)

        md_file = text_path / file_name
        if not md_file.exists():
            report[json_file.name] = {
                "target_file": file_name,
                "status": "missing_text_file",
                "present": [],
                "missing": expected_values,
            }
            total_terms += len(expected_values)
            continue

        text = md_file.read_text(encoding="utf-8", errors="ignore").lower()
        present: list[str] = []
        missing: list[str] = []

        for value in expected_values:
            total_terms += 1
            if value.lower() in text:
                matched_terms += 1
                present.append(value)
            else:
                missing.append(value)

        report[json_file.name] = {
            "target_file": file_name,
            "status": "ok" if not missing else "partial",
            "present": present,
            "missing": missing,
        }

    print("\nJSON text-search validation summary")
    print(f"JSON files checked: {total_json}")
    print(f"Values checked: {total_terms}")
    print(f"Values found: {matched_terms}")
    print(f"Values missing: {total_terms - matched_terms}")

    missing_files = [k for k, v in report.items() if v["status"] == "missing_text_file"]
    partial_files = [k for k, v in report.items() if v["status"] == "partial"]
    if missing_files:
        print(f"JSONs with missing markdown file: {len(missing_files)}")
    if partial_files:
        print(f"JSONs with one or more missing values: {len(partial_files)}")

    final_report = {
        "summary": {
            "json_files_checked": total_json,
            "values_checked": total_terms,
            "values_found": matched_terms,
            "values_missing": total_terms - matched_terms,
        },
        "details": report,
    }
    report_path = Path(report_output_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(final_report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Saved validation report -> {report_path}")
    return final_report


if __name__ == "__main__":
    run_json_text_search_validation()
