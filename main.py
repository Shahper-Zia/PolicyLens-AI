"""CLI entry point for row-driven PA parameter extraction."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pa_extraction.pipeline import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract structured PA policy parameters.")
    parser.add_argument("--input", default="input.csv", help="Input CSV. First two columns must be file_name and brand.")
    parser.add_argument("--indication", required=True, help="Runtime target indication, e.g. Pso.")
    parser.add_argument("--docs-dir", default="data/extracted_pdfs_mds", help="Directory containing extracted markdown/text docs.")
    parser.add_argument("--rules", default="parameter_rules.md", help="Rules file path. Supports current CSV-like md or JSON.")
    parser.add_argument("--output", default="pa_extraction_output.csv", help="Output CSV path.")
    parser.add_argument("--debug-dir", default="data/pa_extraction_debug", help="Directory for chunk-selection debug JSON.")
    parser.add_argument("--provider", default=None, help="Optional LLM provider override, e.g. gemini or llama.")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM calls and use deterministic heuristic fallback only.")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    run_pipeline(
        input_path=args.input,
        indication=args.indication,
        docs_dir=args.docs_dir,
        rules_path=args.rules,
        output_path=args.output,
        debug_dir=args.debug_dir,
        provider=args.provider,
        use_llm=not args.no_llm,
    )


if __name__ == "__main__":
    main()
