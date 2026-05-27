from src.orchestrator.processor.pdf_processor import PDFProcessor
from src.orchestrator.chunker import relevant_chunker
from src.orchestrator.param_extractor import param_extractor    
import os
from dotenv import load_dotenv
load_dotenv()

from src.config.logging import logger
from src.validation.output_schema import ExtractionResponse, BrandAttribute
from src.config.app_settings import processed_pdf_path

class PolicyOrchestrator:

    def __init__(self):
        logger.info("PolicyOrchestrator initialized")
        self.processed_pdf_path = processed_pdf_path  # Replace with your desired output directory
        self.pdf_processor = PDFProcessor
        self.chunker = relevant_chunker

    async def _save_pdf_to_raw_pdfs(self, pdf_file):
        """
        Save the uploaded PDF file to data/raw_pdfs with its original filename. Create data/raw_pdfs if it doesn't exist.
        """
        raw_pdf_path = os.path.join("data/raw_pdfs", pdf_file.filename)
        os.makedirs(os.path.dirname(raw_pdf_path), exist_ok=True)
        with open(raw_pdf_path, "wb") as f:
            content = await pdf_file.read()
            f.write(content)
        return raw_pdf_path

    def _save_extracted_md(self, pdf_file, extracted_md):
        # now save the extracted md to processed_pdf_path with same name as pdf but .md extension
        pdf_md_filename = pdf_file.filename.split(".")[0] + ".md"
        output_path = os.path.join(self.processed_pdf_path, pdf_md_filename)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(extracted_md)
        logger.info(f"Saved extracted markdown for {pdf_file.filename} to {output_path}")

    async def extract_text_from_pdf(self, pdf_file):
        """
        Also check if pdf md is already extracted and saved in processed_pdf_path. If so, load and return that instead of re-extracting.
        """
        
        pdf_md_filename = pdf_file.filename.split(".")[0] + ".md"
        # previously extracted md files are saved with same name as pdf but with .md extension in processed_pdf_path
        if pdf_md_filename in os.listdir(self.processed_pdf_path):
            logger.info(f"Found existing extracted markdown for {pdf_file.filename}, loading from file")
            #with open(os.path.join(self.processed_pdf_path, pdf_md_filename), "r") as f:
            #    extracted_md = f.read()
            with open(os.path.join(self.processed_pdf_path, pdf_md_filename), "r", encoding="utf-8") as f:
                extracted_md = f.read()
            logger.info(f"Loaded existing extracted markdown for {pdf_file.filename}, length: {len(extracted_md)} characters")
        else:
            logger.info(f"Extracting text from PDF: {pdf_file.filename}")
            pdf_file_path = await self._save_pdf_to_raw_pdfs(pdf_file)
            extracted_md = self.pdf_processor(pdf_file_path).extract_text()
            self._save_extracted_md(pdf_file, extracted_md)
        
        return extracted_md
    
    def extract_brands_from_text(self, text):
        logger.info(f"Extracting brands from text. Text length: {len(text)} characters")
        # Implement brand extraction logic here
        dummy_brand_names = ["TREMFYA", "STELARA"]  # Default brands to look for
        return dummy_brand_names
    
    def split_brand_sections(self, text, brands, indication):
        logger.info(f"Splitting text into sections for brands: {brands}")
        relevant_chunks = relevant_chunker.get_brand_indication_chunks(
            source=text,
            brands=brands,
            indication=indication,
            use_llm_scoring=False,
        )
        if relevant_chunks:
            logger.info(f"Extracted relevant chunks for brands: {list(relevant_chunks.keys())}")
            for brand, payload in relevant_chunks.items():
                logger.info(f"{brand} chunk count: {len(payload.get('chunks', []))}")
                for chunk in payload.get("chunks", []):
                    logger.info(
                    f"{brand} | idx={chunk.get('chunk_index')} | "
                    f"rule_score={chunk.get('score')} | "
                    f"llm_score={chunk.get('llm_score')} | "
                    f"final_score={chunk.get('final_score')} | "
                    f"selection={chunk.get('selection_reason')} | "
                    f"reasons={chunk.get('reasons')} | "
                    f"section={chunk.get('section_title')}"
                )
            return relevant_chunks

        return {
            brand: {
                "brand": brand,
                "indication": indication,
                "selected_sections": [],
                "chunks": [],
                "section_scores": [],
            }
            for brand in brands
        }
    
    def extract_brand_attributes(self, filename, brand_section, brand, indication) -> BrandAttribute:
        logger.info(f"Extracting attributes for brand: {brand}")
        # Implement logic to extract attributes for a given brand section here
        parameters = ['age', 'step_therapy_requirements', 'number_of_steps_brands', 'number_of_steps_generic', 'step_through_phototherapy', 'tb_test_required', 'initial_auth_duration', 'reauthorization_duration', 'reauthorization_required', 'reauthorization_requirements', 'specialist_types', 'quantity_limits', 'access_score']
        rule_content_map = {}
        for param in parameters:
            rule_file = f"{param}".replace(" ", "_") + ".md"
            rule_path = os.path.join("src/orchestrator/rules", rule_file)
            
            if os.path.exists(rule_path):                
                with open(rule_path, "r", encoding="utf-8") as f:
                    rule_content = f.read()
                    value = param_extractor.extract_parameter(brand_section, rule_content)
                    rule_content_map[param] = value
        final_attributes = BrandAttribute(
            filename=filename,
            brand=brand,
            indication=indication,
            **rule_content_map
        )

        dummy_attributes = BrandAttribute(
            filename=filename,
            brand=brand,
            indication=indication,
            age="18+",
            step_therapy_requirements="None",
            number_of_steps_brands="0",
            number_of_steps_generic="0",
            step_through_phototherapy="No",
            tb_test_required="No",
            initial_auth_duration="12 months",
            reauthorization_duration="12 months",
            reauthorization_required="Yes",
            reauthorization_requirements="Same as initial",
            specialist_types="Dermatologist, Rheumatologist",
            quantity_limits="Up to 4 syringes per month",
            access_score="8/10"
        )
        if not final_attributes:
            logger.warning(f"Failed to extract attributes for brand: {brand}, returning dummy attributes")
            return dummy_attributes
        return final_attributes

    def extract_attributes(self, filename, brand_sections) -> ExtractionResponse:
        logger.info(f"Extracting attributes from brand sections.")
        dummy_attributes = []
        for brand, payload in brand_sections.items():
            chunks = payload.get("chunks", []) if isinstance(payload, dict) else payload
            brand_section = "\n".join(
                chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
                for chunk in chunks
            )
            indication = payload.get("indication", "N/A") if isinstance(payload, dict) else "Psoriasis"
            attributes = self.extract_brand_attributes(filename, brand_section, brand, indication)
            dummy_attributes.append(attributes)
        return dummy_attributes

    async def process_pdf(self, pdf_file, brand_names=None, indication="Psoriasis") -> ExtractionResponse:

        # Step 1: Extract text from PDF
        extracted_md = await self.extract_text_from_pdf(pdf_file)

        # Step 2: Process extracted text to identify brands
        if not brand_names:
            logger.info("No brand names provided, using default list")
            brand_names = self.extract_brands_from_text(extracted_md)
        else:
            brand_names = [brand.strip() for brand in brand_names.split(",")]
            logger.info(f"Using provided brand names: {brand_names}")

        # Step 3: Extract brands chunks from text
        brand_sections = self.split_brand_sections(extracted_md, brand_names, indication)
        if brand_sections:
            logger.info(f"Extracted brand sections for brands: {list(brand_sections.keys())}")

        # Step 4: Extract attributes for each brand section
        brand_attributes = self.extract_attributes(pdf_file.filename, brand_sections)

        # Step 5: Compile results into response model
        response = ExtractionResponse(
            filename=pdf_file.filename,
            detected_brands=brand_names,
            brand_attributes=brand_attributes
        )

        return response
