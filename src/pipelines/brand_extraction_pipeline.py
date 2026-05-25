"""Pipeline for extracting unique drug brands from markdown files."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List

from services.brand_extraction_service import extract_brands_from_markdown


def run_brand_extraction_pipeline(
    input_dir: str | Path = "data/extracted_pdfs_mds",
    output_dir: str | Path = "data/brand_file_univ",
    failed_log_path: str | Path = "data/brand_file_univ/failed_brand_extraction.txt",
    provider: str | None = None,
    max_retries: int = 3,
) -> Dict[str, List[str]]:
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    failed_log_file = Path(failed_log_path)
    brand_dict: Dict[str, List[str]] = {}

    output_path.mkdir(parents=True, exist_ok=True)
    failed_log_file.parent.mkdir(parents=True, exist_ok=True)

    for md_file in sorted(input_path.glob("*.md")):
        last_error: str | None = None
        for attempt in range(1, max_retries + 1):
            try:
                result = extract_brands_from_markdown(md_file, provider=provider)
                brand_dict.update(result)

                brands = result.get(md_file.name, [])
                output_file = output_path / f"{md_file.stem}.json"
                output_file.write_text(
                    json.dumps(
                        {
                            "file_name": md_file.name,
                            "brands": brands,
                        },
                        indent=2,
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                print(f"Saved brands for {md_file.name} -> {output_file.name}")
                break
            except Exception as exc:
                last_error = str(exc)
                print(f"Attempt {attempt}/{max_retries} failed for {md_file.name}: {last_error}")
                if attempt < max_retries:
                    time.sleep(2 * attempt)
                else:
                    with failed_log_file.open("a", encoding="utf-8") as handle:
                        handle.write(f"{md_file.name} | {last_error}\n")
                    print(f"Logged permanent failure for {md_file.name}")

    return brand_dict
