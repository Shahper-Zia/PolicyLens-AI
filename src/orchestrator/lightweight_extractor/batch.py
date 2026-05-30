import csv
from pathlib import Path
from typing import Dict, List

from src.config.app_settings import processed_pdf_path
from src.orchestrator.lightweight_extractor import LightweightPolicyExtractor


OUTPUT_COLUMNS = [
    "Filename",
    "Brand",
    "Age",
    "Step Therapy Requirements Documented in Policy",
    "Number of Steps through Brands",
    "Number of Steps through Generic",
    "Step through-Phototherapy",
    "TB Test required",
    "Quantity Limits",
    "Specialist Types",
    "Initial Authorization Duration(in-months)",
    "Reauthorization Duration(in-months)",
    "Reauthorization Required",
    "Reauthorization Requirements Documented in Policy",
    "Access Score",
]


def run_lightweight_batch(
    submissions_csv: str = "submissions.csv",
    output_csv: str = "result_lightweight.csv",
    indication: str = "Psoriasis",
) -> str:
    rows = _read_submission_rows(submissions_csv)
    extractor = LightweightPolicyExtractor()
    output_rows: List[Dict[str, str]] = []

    for row in rows:
        filename = row["Filename"].strip()
        brand = row["Brand"].strip()
        markdown_text = _read_markdown(filename)
        response = extractor.extract(filename, markdown_text, [brand], indication=indication)
        output_rows.append(_brand_attribute_to_row(response.brand_attributes[0]))

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(output_rows)

    return output_csv


def _read_submission_rows(submissions_csv: str) -> List[Dict[str, str]]:
    with open(submissions_csv, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        reader.fieldnames = [field.strip() for field in reader.fieldnames or []]
        rows = []
        for row in reader:
            normalized = {key.strip(): (value or "").strip() for key, value in row.items()}
            if normalized.get("Filename") and normalized.get("Brand"):
                rows.append(normalized)
        return rows


def _read_markdown(filename: str) -> str:
    md_filename = Path(filename).with_suffix(".md").name
    md_path = Path(processed_pdf_path) / md_filename
    with open(md_path, "r", encoding="utf-8") as f:
        return f.read()


def _brand_attribute_to_row(attribute) -> Dict[str, str]:
    return {
        "Filename": attribute.filename,
        "Brand": attribute.brand,
        "Age": attribute.age,
        "Step Therapy Requirements Documented in Policy": attribute.step_therapy_requirements,
        "Number of Steps through Brands": attribute.number_of_steps_brands,
        "Number of Steps through Generic": attribute.number_of_steps_generic,
        "Step through-Phototherapy": attribute.step_through_phototherapy,
        "TB Test required": attribute.tb_test_required,
        "Quantity Limits": attribute.quantity_limits,
        "Specialist Types": attribute.specialist_types,
        "Initial Authorization Duration(in-months)": attribute.initial_auth_duration,
        "Reauthorization Duration(in-months)": attribute.reauthorization_duration,
        "Reauthorization Required": attribute.reauthorization_required,
        "Reauthorization Requirements Documented in Policy": attribute.reauthorization_requirements,
        "Access Score": attribute.access_score,
    }


if __name__ == "__main__":
    print(run_lightweight_batch())
