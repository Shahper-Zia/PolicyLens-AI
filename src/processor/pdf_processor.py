import re
import os
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode, TableStructureOptions
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

class PDFProcessor:
    def __init__(self, pdf_path, processed_pdf_path=None):
        self.pdf_path = pdf_path
        self.processed_pdf_path = processed_pdf_path

    def _clean_text(self, text):
        text = text.replace("\x00", " ") # Replace null characters with spaces and normalize whitespace
        text = re.sub(r"\s+", " ", text) # Replace multiple whitespace characters with a single space
        text = re.sub(r"[-=]{3,}", " ", text) # Replace sequences of 3 or more hyphens or equal signs with a single space
        cleaned_text = text.strip()  # remove leading/trailing whitespace
        return cleaned_text

    def _with_docling(self):
        print(f"Processing PDF with docling: {self.pdf_path}")
        pipeline_options = PdfPipelineOptions(
            do_ocr=False,
            do_table_structure=True,
            generate_picture_images=False,
            do_picture_description=False,
            table_structure_options=TableStructureOptions(
                mode=TableFormerMode.FAST
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
        raw_markdown = doc.export_to_markdown()
        cleaned_text = self._clean_text(raw_markdown)

        print(f"Finished processing PDF with docling: {self.pdf_path}")
        return raw_markdown, cleaned_text


    def extract_text(self)-> str:
        """
        Extract text from the PDF file using docling and save it as a markdown file in the processed_pdf_path directory.
        """
        pdf_name =  (os.path.basename(self.pdf_path)).split('.')[0]  # Get the file name without extension
        print(f"Extracting text from PDF: {pdf_name}")

        raw_markdown, _cleaned_text = self._with_docling()

        print(f"Extracted text from PDF: {pdf_name}")
        # saving md text to output file path
        file_path = f"{self.processed_pdf_path}/{pdf_name}.md"
        if self.processed_pdf_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(raw_markdown)
        return raw_markdown
        
    
    @staticmethod
    def validate_pdf(pdf_path):
        if not pdf_path.endswith('.pdf'):
            raise ValueError("Invalid file format. Only PDF files are allowed.")
        
        # check if pdf is empty or not
        # In a real implementation, you would check the file size or attempt to read the PDF
        return True
