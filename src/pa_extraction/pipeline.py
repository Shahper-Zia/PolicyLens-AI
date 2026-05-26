"""Production-style row-driven PA parameter extraction pipeline."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.pa_extraction.documents import build_contextual_chunks, parse_document_into_sections, read_document
from src.pa_extraction.extraction import extract_group_fields
from src.pa_extraction.postprocess import fallback_record, post_process_extraction, validate_output_record
from src.pa_extraction.rules import load_rules
from src.pa_extraction.scoring import build_extraction_context, get_relevant_chunks_for_parameter_group

LOGGER = logging.getLogger(__name__)


def load_input_csv(input_path: str | Path) -> pd.DataFrame:
    """Load row-driven input and normalize the first two columns."""

    df = pd.read_csv(input_path, dtype=str).fillna("")
    if df.shape[1] < 2:
        raise ValueError("Input CSV must contain at least file_name and brand columns.")
    first, second = df.columns[:2]
    df = df.rename(columns={first: "file_name", second: "brand"})
    df["file_name"] = df["file_name"].astype(str).str.strip()
    df["brand"] = df["brand"].astype(str).str.strip()
    return df


def run_pipeline(
    input_path: str | Path,
    indication: str,
    docs_dir: str | Path = "data/extracted_pdfs_mds",
    rules_path: str | Path = "parameter_rules.md",
    output_path: str | Path = "pa_extraction_output.csv",
    debug_dir: str | Path | None = "data/pa_extraction_debug",
    provider: str | None = None,
    use_llm: bool = True,
) -> list[dict[str, str]]:
    """Process input rows and write schema-valid extraction output."""

    rules = load_rules(rules_path)
    input_df = load_input_csv(input_path)
    output_records: list[dict[str, str]] = []
    debug_path = Path(debug_dir) if debug_dir else None
    if debug_path:
        debug_path.mkdir(parents=True, exist_ok=True)

    for row_number, row in input_df.iterrows():
        file_name = str(row["file_name"]).strip()
        brand = str(row["brand"]).strip()
        LOGGER.info("Processing row %s: file=%s brand=%s indication=%s", row_number + 1, file_name, brand, indication)
        try:
            record = process_row(
                file_name=file_name,
                brand=brand,
                indication=indication,
                docs_dir=docs_dir,
                rules=rules,
                debug_dir=debug_path,
                provider=provider,
                use_llm=use_llm,
            )
        except Exception as exc:  # noqa: BLE001 - row failures must not stop the batch.
            LOGGER.exception("Row %s failed for %s/%s: %s", row_number + 1, file_name, brand, exc)
            record = fallback_record(file_name, brand)

        validated = validate_output_record(record)
        output_records.append(_model_to_dict(validated))

    output_df = pd.DataFrame(output_records)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(output_path, index=False)
    LOGGER.info("Wrote %s extracted rows to %s", len(output_records), output_path)
    return output_records


def process_row(
    file_name: str,
    brand: str,
    indication: str,
    docs_dir: str | Path,
    rules: Any,
    debug_dir: Path | None = None,
    provider: str | None = None,
    use_llm: bool = True,
) -> dict[str, str]:
    """Process exactly one file/brand/indication target scope."""

    document_path, document_text = read_document(file_name, docs_dir)
    sections = parse_document_into_sections(document_text)
    chunks = build_contextual_chunks(sections)
    context = build_extraction_context(file_name=file_name, brand=brand, indication=indication, rules=rules)

    raw_record: dict[str, Any] = {"filename": file_name, "brand": brand}
    debug_payload: dict[str, Any] = {
        "file_name": file_name,
        "resolved_document": str(document_path),
        "brand": brand,
        "indication": indication,
        "section_count": len(sections),
        "chunk_count": len(chunks),
        "groups": {},
    }

    for group_name in rules.groups:
        group_chunks = get_relevant_chunks_for_parameter_group(chunks, group_name, rules, context)
        debug_payload["groups"][group_name] = [
            {
                "chunk_index": chunk.chunk_index,
                "score": chunk.score,
                "reasons": list(chunk.reasons),
                "section_title": chunk.section_title,
                "section_type": chunk.section_type,
                "start": chunk.start,
                "end": chunk.end,
                "preview": chunk.text[:700],
            }
            for chunk in group_chunks
        ]
        group_values = extract_group_fields(
            group_name=group_name,
            chunks=group_chunks,
            rules=rules,
            context=context,
            provider=provider,
            use_llm=use_llm,
        )
        raw_record.update(group_values)

    final_record = post_process_extraction(raw_record)
    if debug_dir:
        _write_debug_file(debug_dir, file_name, brand, indication, debug_payload, final_record)
    return _model_to_dict(validate_output_record(final_record))


def _write_debug_file(
    debug_dir: Path,
    file_name: str,
    brand: str,
    indication: str,
    debug_payload: dict[str, Any],
    final_record: dict[str, str],
) -> None:
    import json
    import re

    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{Path(file_name).stem}_{brand}_{indication}")
    payload = {**debug_payload, "final_record": final_record}
    (debug_dir / f"{safe_name}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _model_to_dict(model: Any) -> dict[str, str]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
