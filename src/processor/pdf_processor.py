import os
import re
from pathlib import Path

import fitz
import pymupdf.layout
import pymupdf4llm
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableFormerMode,
    TableStructureOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption


class PDFProcessor:
    def __init__(
        self,
        pdf_path,
        processed_pdf_path=None,
        *,
        do_ocr=True,
        table_mode="accurate",
        force_backend_text=False,
        export_format="markdown",
        markdown_compact_tables=True,
    ):
        self.pdf_path = pdf_path
        self.processed_pdf_path = processed_pdf_path
        self.do_ocr = bool(do_ocr)
        self.table_mode = str(table_mode).lower()
        self.force_backend_text = bool(force_backend_text)
        self.export_format = str(export_format).lower()
        self.markdown_compact_tables = bool(markdown_compact_tables)

    def _clean_text(self, text):
        text = text.replace("\x00", " ")
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"[-=]{3,}", " ", text)
        return text.strip()

    def _resolve_table_mode(self):
        if self.table_mode == "fast":
            return TableFormerMode.FAST
        return TableFormerMode.ACCURATE

    def _export_document(self, doc):
        if self.export_format == "html":
            return doc.export_to_html()
        if self.export_format == "doctags":
            return doc.export_to_doctags()
        if self.export_format == "text":
            return doc.export_to_text()
        return doc.export_to_markdown(
            strict_text=False,
            compact_tables=self.markdown_compact_tables,
            escape_underscores=False,
        )

    def _with_docling(self):
        print(f"Processing PDF with docling: {self.pdf_path}")
        pipeline_options = PdfPipelineOptions(
            do_ocr=self.do_ocr,
            do_table_structure=True,
            generate_picture_images=False,
            do_picture_description=False,
            force_backend_text=self.force_backend_text,
            table_structure_options=TableStructureOptions(
                mode=self._resolve_table_mode(),
                do_cell_matching=True,
            ),
        )
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options,
                    backend=PyPdfiumDocumentBackend,
                )
            }
        )

        result = converter.convert(self.pdf_path)
        doc = result.document
        extracted_content = self._export_document(doc)
        cleaned_text = self._clean_text(extracted_content)

        print(f"Finished processing PDF with docling: {self.pdf_path}")
        return extracted_content, cleaned_text

    def extract_text(self) -> str:
        """
        Extract text from PDF and save Markdown output when output path is set.
        """
        pdf_name = os.path.splitext(os.path.basename(self.pdf_path))[0]
        print(f"Extracting text from PDF: {pdf_name}")

        extracted_content = self.extract_text_with_pymupdf()

        print(f"Extracted text from PDF: {pdf_name}")
        if self.processed_pdf_path:
            file_path = f"{self.processed_pdf_path}/{pdf_name}.md"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(extracted_content)

        return extracted_content

    def _extract_with_pymupdf4llm(self, pdf_path: Path, *, use_layout: bool) -> str:
        pymupdf4llm.use_layout(use_layout)
        try:
            return pymupdf4llm.to_markdown(
                str(pdf_path),
                page_separators=True,
                force_text=True,
                ignore_images=True,
                ignore_graphics=True,
                table_strategy="lines_strict",
                show_progress=False,
            )
        finally:
            pymupdf4llm.use_layout(False)

    def _extract_with_pymupdf_blocks(self, pdf_path: Path) -> str:
        pages = []
        doc = fitz.open(str(pdf_path))
        try:
            for page_number, page in enumerate(doc, start=1):
                blocks = page.get_text("blocks", sort=True)
                text_blocks = []
                for block in blocks:
                    if len(block) < 5:
                        continue
                    text = block[4].strip()
                    if text:
                        text_blocks.append(text)

                pages.append(f"<!-- page {page_number} -->\n" + "\n\n".join(text_blocks))
        finally:
            doc.close()

        return "\n\n".join(pages)

    def extract_text_with_pymupdf(self) -> str:
        """Extract Markdown using PyMuPDF4LLM with PyMuPDF layout fallback paths."""
        pdf_path = Path(self.pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"No file found at {pdf_path}")

        print(f"Extracting PDF with PyMuPDF/PyMuPDF4LLM: {pdf_path}")

        extractors = [
            ("pymupdf4llm-layout", lambda: self._extract_with_pymupdf4llm(pdf_path, use_layout=True)),
            ("pymupdf4llm", lambda: self._extract_with_pymupdf4llm(pdf_path, use_layout=False)),
            ("pymupdf-blocks", lambda: self._extract_with_pymupdf_blocks(pdf_path)),
        ]

        errors = []
        for name, extractor in extractors:
            try:
                content = extractor().strip()
                if content:
                    print(f"Extracted PDF using {name}")
                    return content + "\n"
                errors.append(f"{name}: empty output")
            except Exception as exc:
                errors.append(f"{name}: {exc}")

        raise RuntimeError("PyMuPDF extraction failed. " + " | ".join(errors))

    def extract_layout_text(self) -> str:
        return self.extract_text_with_pymupdf()

    def extract__text_with_pymupdf(self) -> str:
        return self.extract_text_with_pymupdf()

    @staticmethod
    def validate_pdf(pdf_path):
        if Path(pdf_path).suffix.lower() != ".pdf":
            raise ValueError("Invalid file format. Only PDF files are allowed.")
        return True
