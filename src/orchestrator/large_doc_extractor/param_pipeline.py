import argparse
from contextlib import redirect_stdout
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any, Dict, Optional

from src.orchestrator.large_doc_extractor.extractor import LargeDocPolicyExtractor


def run_param_pipeline(
    markdown_file: str,
    brand: str,
    filename: Optional[str] = None,
    indication: str = "Psoriasis",
    output_dir: str = "outputs/large_doc_extractor",
    use_llm_vocabulary: bool = True,
    verbose: bool = True,
) -> Dict[str, Any]:
    markdown_path = Path(markdown_file)
    markdown_text = markdown_path.read_text(encoding="utf-8")
    file_name = filename or markdown_path.with_suffix(".pdf").name
    output_path = _output_path(output_dir, file_name, brand)
    log_path = _log_path(output_dir, file_name, brand)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("w", encoding="utf-8") as log_file:
        stream = _TeeStream(sys.stdout, log_file) if verbose else log_file
        with redirect_stdout(stream):
            print(f"[{_timestamp()}] Starting param pipeline", flush=True)
            print(f"[{_timestamp()}] markdown_file={markdown_path}", flush=True)
            print(f"[{_timestamp()}] file_name={file_name}", flush=True)
            print(f"[{_timestamp()}] brand={brand}", flush=True)
            print(f"[{_timestamp()}] indication={indication}", flush=True)
            print(f"[{_timestamp()}] output_path={output_path}", flush=True)
            print(f"[{_timestamp()}] log_path={log_path}", flush=True)

            extractor = LargeDocPolicyExtractor(
                verbose=True,
                use_llm_vocabulary=use_llm_vocabulary,
            )
            response = extractor.extract(
                filename=file_name,
                markdown_text=markdown_text,
                brand_names=[brand],
                indication=indication,
            )
            print(f"[{_timestamp()}] Extraction completed", flush=True)

    brand_attribute = response.brand_attributes[0].model_dump()
    output = {
        "file_name": file_name,
        "brand": brand,
        "brand_attributes": brand_attribute,
        "extraction": response.model_dump(),
        "decision_context": extractor.last_contexts.get((file_name, brand), {}),
        "log_file": str(log_path),
    }

    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    if verbose:
        print(f"Saved output -> {output_path}", flush=True)
        print(f"Saved log -> {log_path}", flush=True)

    return output


def main():
    parser = argparse.ArgumentParser(description="Run parameter extraction for one markdown file and brand.")
    parser.add_argument("markdown_file", help="Path to extracted policy markdown file.")
    parser.add_argument("brand", help="Target brand, such as TREMFYA or STELARA.")
    parser.add_argument("--filename", help="Original PDF filename to put in output.")
    parser.add_argument("--indication", default="Psoriasis", help="Target indication.")
    parser.add_argument(
        "--output-dir",
        default="outputs/large_doc_extractor",
        help="Directory where extraction JSON outputs are saved.",
    )
    parser.add_argument(
        "--no-llm-vocabulary",
        action="store_true",
        help="Use deterministic vocabulary scan only; skip vocabulary cleanup LLM call.",
    )
    args = parser.parse_args()

    output = run_param_pipeline(
        markdown_file=args.markdown_file,
        brand=args.brand,
        filename=args.filename,
        indication=args.indication,
        output_dir=args.output_dir,
        use_llm_vocabulary=not args.no_llm_vocabulary,
        verbose=True,
    )
    print(json.dumps(output, indent=2, ensure_ascii=False))


def _output_path(output_dir: str, filename: str, brand: str) -> Path:
    safe_filename = Path(filename).stem.replace(" ", "_")
    safe_brand = brand.strip().replace("/", "_").replace(" ", "_")
    return Path(output_dir) / f"{safe_filename}_{safe_brand}.json"


def _log_path(output_dir: str, filename: str, brand: str) -> Path:
    safe_filename = Path(filename).stem.replace(" ", "_")
    safe_brand = brand.strip().replace("/", "_").replace(" ", "_")
    return Path(output_dir) / "log_folder" / f"{safe_filename}_{safe_brand}.log"


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class _TeeStream:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for stream in self.streams:
            stream.write(data)
            stream.flush()

    def flush(self):
        for stream in self.streams:
            stream.flush()


if __name__ == "__main__":
    main()
