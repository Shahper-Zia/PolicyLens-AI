import re
import time
import signal
import logging
import gc

from pathlib import Path

from docling.document_converter import (
    DocumentConverter,
    PdfFormatOption,
)

from docling.datamodel.base_models import InputFormat

from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableFormerMode,
    TableStructureOptions,
)

# IMPORTANT FIX
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

# ── CONFIG ──────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parents[1]

PDF_FOLDER = BASE_DIR / "data" / "raw_pdfs"

BASE_OUTPUT_FOLDER = BASE_DIR / "data" / "extracted_pdfs"

RAW_MD_FOLDER = BASE_OUTPUT_FOLDER / "raw_markdown"

CLEAN_TEXT_FOLDER = BASE_OUTPUT_FOLDER / "cleaned_text"

TIMEOUT_SECONDS = 5 * 60  # 20 mins

# ── CREATE OUTPUT FOLDERS ──────────────────────────────

RAW_MD_FOLDER.mkdir(parents=True, exist_ok=True)

CLEAN_TEXT_FOLDER.mkdir(parents=True, exist_ok=True)

# ── LOGGING ────────────────────────────────────────────

logging.getLogger().setLevel(logging.ERROR)

SKIPPED_LOG_FILE = BASE_OUTPUT_FOLDER / "skipped_files.log"

# ── CLEAN TEXT FUNCTION ────────────────────────────────

def clean_text(text):

    text = text.replace("\x00", " ")

    text = re.sub(r"\s+", " ", text)

    text = re.sub(r"[-=]{3,}", " ", text)

    return text.strip()

# ── TIMEOUT HANDLER ────────────────────────────────────

class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException()

signal.signal(signal.SIGALRM, timeout_handler)

# ── PIPELINE OPTIONS ───────────────────────────────────

pipeline_options = PdfPipelineOptions(

    do_ocr=False,

    do_table_structure=True,

    generate_picture_images=False,

    do_picture_description=False,

    table_structure_options=TableStructureOptions(
        mode=TableFormerMode.FAST
    ),
)

# ── CONVERTER FACTORY ──────────────────────────────────

def create_converter():

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,

                # IMPORTANT FIX
                backend=PyPdfiumDocumentBackend,
            )
        }
    )

# initial converter
converter = create_converter()

# ── SKIP LOGIC ─────────────────────────────────────────

completed_files = {
    f.stem for f in RAW_MD_FOLDER.glob("*.md")
}

print(f"Already completed: {len(completed_files)}")

# ── PROCESS PDFs ───────────────────────────────────────

c = 0
processed_counter = 0

for pdf in PDF_FOLDER.glob("*.pdf"):

    # skip already completed
    if pdf.stem in completed_files:
        print(f"Skipping completed: {pdf.name}")
        continue

    c += 1

    print(f"\nsl: {c} | {pdf.name} extraction started")

    try:

        # refresh converter every 10 REAL processed PDFs
        if processed_counter > 0 and processed_counter % 10 == 0:

            print("\nRefreshing converter to free memory...\n")

            del converter

            gc.collect()

            converter = create_converter()

        # timeout start
        signal.alarm(TIMEOUT_SECONDS)

        start_time = time.time()

        # ── CONVERT PDF ───────────────────────────────

        result = converter.convert(pdf)

        doc = result.document

        # ── EXPORT MARKDOWN ───────────────────────────

        raw_markdown = doc.export_to_markdown()

        cleaned_text = clean_text(raw_markdown)

        # ── SAVE MARKDOWN ────────────────────────────

        raw_md_file = RAW_MD_FOLDER / f"{pdf.stem}.md"

        with open(raw_md_file, "w", encoding="utf-8") as f:
            f.write(raw_markdown)

        # ── SAVE CLEAN TEXT ──────────────────────────

        clean_txt_file = CLEAN_TEXT_FOLDER / f"{pdf.stem}.txt"

        with open(clean_txt_file, "w", encoding="utf-8") as f:
            f.write(cleaned_text)

        # stop timeout
        signal.alarm(0)

        elapsed = round(time.time() - start_time, 2)

        print(f"Completed | Time: {elapsed} sec")

        processed_counter += 1

        # ── MEMORY CLEANUP ──────────────────────────

        for var in [
            "result",
            "doc",
            "raw_markdown",
            "cleaned_text"
        ]:
            try:
                del globals()[var]
            except:
                pass

        gc.collect()

    except TimeoutException:

        signal.alarm(0)

        msg = f"TIMEOUT (>20 mins) | {pdf.name}"

        print(msg)

        with open(SKIPPED_LOG_FILE, "a", encoding="utf-8") as logf:
            logf.write(msg + "\n")

        for var in [
            "result",
            "doc",
            "raw_markdown",
            "cleaned_text"
        ]:
            try:
                del globals()[var]
            except:
                pass

        gc.collect()

    except Exception as e:

        signal.alarm(0)

        msg = f"ERROR | {pdf.name} | {str(e)}"

        print(msg)

        with open(SKIPPED_LOG_FILE, "a", encoding="utf-8") as logf:
            logf.write(msg + "\n")

        for var in [
            "result",
            "doc",
            "raw_markdown",
            "cleaned_text"
        ]:
            try:
                del globals()[var]
            except:
                pass

        gc.collect()

print("\nAll processing completed.")