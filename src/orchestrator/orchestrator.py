from asyncio import log
from webbrowser import get

import pandas as pd

from src.orchestrator.processor.pdf_processor import PDFProcessor
import os
from dotenv import load_dotenv
load_dotenv()

from src.config.logging import logger
from src.validation.output_schema import ExtractionResponse, BrandAttribute
from src.config.app_settings import processed_pdf_path
from src.orchestrator.kg_maker import kg_maker
from src.orchestrator.param_extractor import param_extractor
from src.orchestrator.large_doc_extractor.param_pipeline import run_param_pipeline
from src.orchestrator.access_score_calculator import access_scorer

class PolicyOrchestrator:

    def __init__(self):
        logger.info("PolicyOrchestrator initialized")
        self.processed_pdf_path = processed_pdf_path  # Replace with your desired output directory
        self.pdf_processor = PDFProcessor
        self.param_pipeline = run_param_pipeline
        self.calculate_access_score = access_scorer.calculate_access_score

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
            with open(os.path.join(self.processed_pdf_path, pdf_md_filename), "r") as f:
                extracted_md = f.read()
            logger.info(f"Loaded existing extracted markdown for {pdf_file.filename}, length: {len(extracted_md)} characters")
        else:
            logger.info(f"Extracting text from PDF: {pdf_file.filename}")
            pdf_file_path = await self._save_pdf_to_raw_pdfs(pdf_file)
            extracted_md = self.pdf_processor(pdf_file_path).extract_text()
            self._save_extracted_md(pdf_file, extracted_md)
        
        return extracted_md
    
    def clean_extracted_text(self, text):
        logger.info(f"Cleaning extracted text. Original length: {len(text)} characters")
        # Implement text cleaning logic here (e.g., remove extra whitespace, fix encoding issues)
        cleaned_text = " ".join(text.split())
        logger.info(f"Cleaned extracted text. Cleaned length: {len(cleaned_text)} characters")
        return cleaned_text
    
    #this function calls the extractor retriever to get the extracted attributes for a given brand in a filename and indication
    def exctractor_retriver(self, file_name, brand, indication):
        logger.info(f"Extracting attributes for brand: {brand} and indication: {indication}")
        file_name = file_name.split(".")[0] + ".md"  # Ensure we are using the .md version of the file
        result = self.param_pipeline(
            markdown_file=file_name,
            brand=brand,
            indication=indication or "Psoriasis (PSo)",
        )
        return result
    
    def access_score_adder(self, file_name,brand) -> str:
        logger.info(f"Calculating access score for brand: {brand}")
        # Implement access score calculation logic here based on the extracted attributes
        # For demonstration, we'll return a dummy access score
        result = access_scorer.calculate_access_score(file_name,brand)
        return result
    
    def output_filler(self, result, submit):
        logger.info(f"Filling output with extracted attributes and access score.")
        df = pd.read_csv(submit)

        column_lookup = {column.strip(): column for column in df.columns}
        field_to_header = {
            "filename": "Filename",
            "brand": "Brand",
            "age": "Age",
            "step_therapy_requirements": "Step Therapy Requirements Documented in Policy",
            "number_of_steps_brands": "Number of Steps through Brands",
            "number_of_steps_generic": "Number of Steps through Generic",
            "step_through_phototherapy": "Step through-Phototherapy",
            "tb_test_required": "TB Test required",
            "quantity_limits": "Quantity Limits",
            "specialist_types": "Specialist Types",
            "initial_auth_duration": "Initial Authorization Duration(in-months)",
            "reauthorization_duration": "Reauthorization Duration(in-months)",
            "reauthorization_required": "Reauthorization Required",
            "reauthorization_requirements": "Reauthorization Requirements Documented in Policy",
            "access_score": "Access Score",
        }

        if "brand_attributes" in result:
            brand_attributes = result["brand_attributes"]
        else:
            first_result = next(iter(result.values()))
            brand_attributes = first_result["brand_attributes"]

        filename = str(brand_attributes.get("filename") or result.get("file_name") or "").strip()
        brand = str(brand_attributes.get("brand") or result.get("brand") or "").strip()

        filename_column = column_lookup["Filename"]
        brand_column = column_lookup["Brand"]
        row_mask = (
            df[filename_column].astype(str).str.strip().str.lower().eq(filename.lower())
            & df[brand_column].astype(str).str.strip().str.lower().eq(brand.lower())
        )

        if not row_mask.any():
            df.loc[len(df)] = {column: "" for column in df.columns}
            row_mask = df.index == df.index[-1]

        for field_name, header in field_to_header.items():
            column = column_lookup.get(header)
            if column is None:
                logger.warning(f"Skipping missing output column: {header}")
                continue
            value = brand_attributes.get(field_name, "")
            df.loc[row_mask, column] = "" if value is None else str(value)

        output_dir = os.path.join("outputs", "filled_submissions")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(
            output_dir,
            os.path.splitext(os.path.basename(submit))[0] + "_filled.csv",
        )
        df.to_csv(output_path, index=False)
        logger.info(f"Saved filled output CSV to {output_path}")
        return output_path
    
    """
    #Build graph once per unique PDF
    def make_graph():
        df = pd.read_csv("submissions.csv") 
        unique_files = df.iloc[:, 0].dropna().unique()
        for file_name in unique_files:
            log(f"n######## BUILDING GRAPH FOR {file_name} ########")
            status = kg_maker.build_graph_if_needed(file_name, force_rebuild=False)
            if not status:
                log(f"ERROR building graph for {file_name}. Skipping to next file.")
                continue
            log(f"Graph ready for {file_name}")
        return status
    """
    """
    def extract_brands_from_text(self, text):
        logger.info(f"Extracting brands from text. Text length: {len(text)} characters")
        # Implement brand extraction logic here
        dummy_brand_names = ["TREMFYA", "STELARA"]  # Default brands to look for
        return dummy_brand_names
    
    def split_brand_sections(self, text, brands, indication):
        logger.info(f"Splitting text into sections for brands: {brands}")
        # Implement logic to split text into brand-specific sections here
        dummy_sections = {brand: [f"Extracted section {i+1} for {brand} and {indication}" for i in range(3)] for brand in brands}
        return dummy_sections
    

    def extract_brand_attributes(self, file_name, brand, indication, result) -> BrandAttribute:
        logger.info(f"Extracting attributes for brand: {brand}")
        # Implement logic to extract attributes for a given brand section here
        extraction_path = find_large_doc_output(file_name, brand, output_dir=output_dir)
        brand_attributes = load_brand_attributes(extraction_path)

    def extract_attributes(self, filename, brand_sections, indication) -> ExtractionResponse:
        logger.info(f"Extracting attributes from brand sections.")
        # Implement logic to extract attributes for each brand section based on indication here
        dummy_attributes = []
        for brand, sections in brand_sections.items():
            brand_section = "\n".join(sections)
            attributes = self.extract_brand_attributes(filename, brand_section, brand, indication)
            dummy_attributes.append(attributes)
        return dummy_attributes
    """
    async def process_pdf(self, pdf_file, brand_names=None, indication="Psoriasis") -> ExtractionResponse:

        # Step 1: Extract text from PDF
        extracted_md = await self.extract_text_from_pdf(pdf_file)
        """
        # Step 2: Process extracted text to identify brands
        if not brand_names:
            logger.info("No brand names provided, using default list")
            brand_names = self.extract_brands_from_text(extracted_md)
        else:
            brand_names = [brand.strip() for brand in brand_names.split(",")]
            logger.info(f"Using provided brand names: {brand_names}")
        
        brand_name = [brand.strip() for brand in brand_names.split(",")]
        logger.info(f"Using provided brand names: {brand_names}")
        """
        # Step 3: Extract brands chunks from text
        brand_sections = self.split_brand_sections(extracted_md, brand_names, indication)

        # Step 4: Extract attributes for each brand section
        brand_attributes = self.extract_attributes(pdf_file.filename, brand_sections, indication)

        # Step 5: Compile results into response model
        response = ExtractionResponse(
            filename=pdf_file.filename,
            detected_brands=brand_names,
            brand_attributes=brand_attributes
        )

        return response
