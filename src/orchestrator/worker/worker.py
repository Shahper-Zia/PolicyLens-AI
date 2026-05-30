from pathlib import Path

from src.orchestrator.kg_maker.kg_maker import build_graph_if_needed
from src.orchestrator.param_extractor.param_extractor import (
    DEFAULT_RESULTS_DIR,
    query_existing_graph,
)


def run_policy_extraction(
    pdf_filename,
    brand_name,
    results_dir=DEFAULT_RESULTS_DIR,
    force_rebuild=False,
):
    graph_ready = build_graph_if_needed(pdf_filename, force_rebuild=force_rebuild)
    if not graph_ready:
        return False

    query_existing_graph(
        file_name=pdf_filename,
        brand_name=brand_name,
        results_dir=Path(results_dir),
    )
    return True
