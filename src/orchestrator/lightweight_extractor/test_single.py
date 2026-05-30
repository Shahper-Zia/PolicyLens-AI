import argparse
import json
from pathlib import Path

from src.orchestrator.lightweight_extractor.chunker import split_markdown
from src.orchestrator.lightweight_extractor.extractor import LightweightPolicyExtractor
from src.orchestrator.lightweight_extractor.retriever import (
    format_context_pack_for_prompt,
    retrieve_rule_aware_context,
)


def main():
    parser = argparse.ArgumentParser(
        description="Test lightweight policy extraction for one markdown file and brand."
    )
    parser.add_argument("markdown_file", help="Path to extracted policy markdown file.")
    parser.add_argument("brand", help="Target brand, such as TREMFYA or STELARA.")
    parser.add_argument("--filename", help="Original PDF filename to put in output.")
    parser.add_argument("--indication", default="Psoriasis", help="Target indication.")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Only print retrieved context; do not call Groq.",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=14,
        help="Maximum global chunks used by the extractor.",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/lightweight_extractor",
        help="Directory where extraction JSON outputs are saved.",
    )
    args = parser.parse_args()

    markdown_path = Path(args.markdown_file)
    markdown_text = markdown_path.read_text(encoding="utf-8")
    filename = args.filename or markdown_path.with_suffix(".pdf").name
    output_path = _output_path(args.output_dir, filename, args.brand)

    if args.no_llm:
        print(f"Retrieving evidence for {filename} | {args.brand} | {args.indication}", flush=True)
        chunks = split_markdown(markdown_text)
        context = retrieve_rule_aware_context(
            chunks=chunks,
            brand=args.brand,
            indication=args.indication,
            max_global_chunks=min(8, args.max_chunks),
            max_chunks_per_field=4,
        )
        print(format_context_pack_for_prompt(context))
        return

    print(f"Starting lightweight extraction for {filename} | {args.brand} | {args.indication}", flush=True)
    print(f"Output will be saved to {output_path}", flush=True)

    extractor = LightweightPolicyExtractor(max_chunks=args.max_chunks, verbose=True)
    response = extractor.extract(
        filename=filename,
        markdown_text=markdown_text,
        brand_names=[args.brand],
        indication=args.indication,
    )
    output = {
        "extraction": response.model_dump(),
        "decision_context": extractor.last_contexts.get((filename, args.brand), {}),
    }
    response_json = json.dumps(output, indent=2, ensure_ascii=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(response_json, encoding="utf-8")

    print(response_json)
    print(f"\nSaved output -> {output_path}")


def _output_path(output_dir: str, filename: str, brand: str) -> Path:
    safe_filename = Path(filename).stem.replace(" ", "_")
    safe_brand = brand.strip().replace("/", "_").replace(" ", "_")
    return Path(output_dir) / f"{safe_filename}_{safe_brand}.json"


if __name__ == "__main__":
    main()
