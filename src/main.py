import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipelines.brand_extraction_pipeline import run_brand_extraction_pipeline
from test.json_tester import run_json_text_search_validation


if __name__ == "__main__":
    """
    result = run_brand_extraction_pipeline(
        input_dir="data/extracted_pdfs_mds",
        output_dir="data/brand_file_univ",
        failed_log_path="data/brand_file_univ/failed_brand_extraction.txt",
        max_retries=3,
    )
    print(f"Processed {len(result)} markdown files.")
    """
    run_json_text_search_validation(
        json_dir="data/brand_file_univ_non_hallucinated",
        text_dir="data/extracted_pdfs_mds",
    )
    print(run_json_text_search_validation)
