# PA Parameter Extraction Implementation Plan

## Goals

- Process `input.csv` row by row using the row's `file_name` and `brand`.
- Accept `indication` at runtime.
- Resolve one extracted policy document per row.
- Chunk policy text by document structure before retrieval.
- Retrieve evidence by brand, indication, rule keywords, section type, inclusion signals, exclusion signals, and proximity.
- Extract parameter groups with narrow prompts rather than one whole-document prompt.
- Validate every final row with `src/validation/output_schema.py`.
- Continue processing after row failures and write schema-compatible fallback rows.

## Runtime Flow

1. `load_input_csv()` normalizes the first two CSV columns to `file_name` and `brand`.
2. `load_rules()` loads either the existing CSV-like `parameter_rules.md` or a richer JSON rules file.
3. `read_document()` resolves `.pdf` input names to matching `.md` or `.txt` extracted documents.
4. `parse_document_into_sections()` splits markdown headings first, with heuristic headings as fallback.
5. `build_contextual_chunks()` creates chunks from section-local paragraphs, bullets, tables, and criteria blocks.
6. `score_chunks_for_parameter()` ranks chunks using target scope and rule-specific hints.
7. `get_relevant_chunks_for_parameter_group()` merges top chunks for fields in each group.
8. `extract_group_fields()` calls the LLM with a group-specific prompt, or uses deterministic fallback if disabled/failing.
9. `post_process_extraction()` normalizes empty values, yes/no values, step counts, phototherapy separation, and reauthorization inference.
10. `validate_output_record()` validates the row against `brandattribute`.

## Project Structure

- `main.py`: root CLI entry point.
- `src/pa_extraction/models.py`: dataclasses for rules, sections, chunks, and extraction context.
- `src/pa_extraction/rules.py`: dynamic rules loading and default parameter grouping.
- `src/pa_extraction/documents.py`: document resolution, section parsing, and contextual chunking.
- `src/pa_extraction/scoring.py`: deterministic relevance scoring and scope filtering.
- `src/pa_extraction/prompts.py`: narrow group extraction prompt builder.
- `src/pa_extraction/extraction.py`: LLM extraction plus heuristic fallback.
- `src/pa_extraction/postprocess.py`: deterministic cleanup, scoring, fallback rows, and Pydantic validation.
- `src/pa_extraction/pipeline.py`: row-driven orchestration and debug artifact writing.
- `config/pa_parameter_rules.sample.json`: richer editable sample rules format with aliases.

## Sample CLI

```powershell
python main.py --input input.csv --indication Pso --docs-dir data/extracted_pdfs_mds --output pa_extraction_output.csv
```

For a deterministic smoke test without LLM calls:

```powershell
python main.py --input input.csv --indication Pso --docs-dir data/extracted_pdfs_mds --output pa_extraction_output.csv --no-llm
```
