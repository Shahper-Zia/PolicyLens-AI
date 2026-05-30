import os
from typing import List, Optional

from dotenv import load_dotenv

from src.config.app_settings import processed_pdf_path
from src.config.logging import logger
from src.orchestrator.lightweight_extractor import LightweightPolicyExtractor
from src.orchestrator.processor.pdf_processor import PDFProcessor
from src.validation.output_schema import ExtractionResponse

load_dotenv()


class LightweightPolicyOrchestrator:
    def __init__(self):
        logger.info("LightweightPolicyOrchestrator initialized")
        self.processed_pdf_path = processed_pdf_path
        self.pdf_processor = PDFProcessor
        self.extractor = LightweightPolicyExtractor()

    async def _save_pdf_to_raw_pdfs(self, pdf_file):
        raw_pdf_path = os.path.join("data/raw_pdfs", pdf_file.filename)
        os.makedirs(os.path.dirname(raw_pdf_path), exist_ok=True)
        with open(raw_pdf_path, "wb") as f:
            content = await pdf_file.read()
            f.write(content)
        return raw_pdf_path

    def _save_extracted_md(self, pdf_file, extracted_md: str):
        pdf_md_filename = pdf_file.filename.rsplit(".", 1)[0] + ".md"
        output_path = os.path.join(self.processed_pdf_path, pdf_md_filename)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(extracted_md)
        logger.info(f"Saved extracted markdown for {pdf_file.filename} to {output_path}")

    async def extract_text_from_pdf(self, pdf_file) -> str:
        pdf_md_filename = pdf_file.filename.rsplit(".", 1)[0] + ".md"
        md_path = os.path.join(self.processed_pdf_path, pdf_md_filename)

        if os.path.exists(md_path):
            logger.info(f"Found existing extracted markdown for {pdf_file.filename}, loading from file")
            with open(md_path, "r", encoding="utf-8") as f:
                return f.read()

        logger.info(f"Extracting text from PDF: {pdf_file.filename}")
        pdf_file_path = await self._save_pdf_to_raw_pdfs(pdf_file)
        extracted_md = self.pdf_processor(pdf_file_path).extract_text()
        self._save_extracted_md(pdf_file, extracted_md)
        return extracted_md

    def extract_brands_from_text(self, text: str) -> List[str]:
        text_lower = text.lower()
        brands = []
        if "tremfya" in text_lower or "guselkumab" in text_lower:
            brands.append("TREMFYA")
        if "stelara" in text_lower or "ustekinumab" in text_lower:
            brands.append("STELARA")
        return brands or ["TREMFYA", "STELARA"]

    async def process_pdf(
        self,
        pdf_file,
        brand_names: Optional[str] = None,
        indication: str = "Psoriasis",
    ) -> ExtractionResponse:
        extracted_md = await self.extract_text_from_pdf(pdf_file)

        if brand_names:
            brands = [brand.strip() for brand in brand_names.split(",") if brand.strip()]
            logger.info(f"Using provided brand names: {brands}")
        else:
            brands = self.extract_brands_from_text(extracted_md)
            logger.info(f"Detected/default brand names: {brands}")

        return self.extractor.extract(
            filename=pdf_file.filename,
            markdown_text=extracted_md,
            brand_names=brands,
            indication=indication,
        )
