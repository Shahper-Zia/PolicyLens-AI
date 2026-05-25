from processor.pdf_processor import PDFProcessor
import os


if __name__ == "__main__":

    """
    csv -> 
    for pdf_name(1), brand_name(1) in csv:
        pdf_name -> pdf_path -> extract text -> output text file path
        output text file path + brand_name -> extract branded chunks 
        -> (12) brand attributes (rule, schema) ->(1) calculate access score 
        -> df.append(brand_attributes)

    df.save_csv()
    """

    processed_pdf_path = "data/extracted_pdfs_mds"  # Replace with your desired output directory

    # Inputs
    pdf_path = "data/raw_pdfs/195158-4643510.pdf"  # Replace with your PDF file path
    brand_name = "TREMFYA"  # Replace with the actual brand name

    # Process PDF and extract text (configurable via env vars)
    pdf_processor = PDFProcessor(
        pdf_path,
        processed_pdf_path,
        do_ocr=os.getenv("DOCLING_DO_OCR", "true").lower() == "true",
        table_mode=os.getenv("DOCLING_TABLE_MODE", "accurate"),  # fast | accurate
        force_backend_text=os.getenv("DOCLING_FORCE_BACKEND_TEXT", "false").lower() == "true",
        export_format=os.getenv("DOCLING_EXPORT_FORMAT", "markdown"),  # markdown | html | doctags | text
        markdown_compact_tables=os.getenv("DOCLING_MD_COMPACT_TABLES", "true").lower() == "true",
    )
    extracted_md = pdf_processor.extract_text()

    # Get brand chunks


    # Get brand attributes


    # Calculate access score


    # Save results to CSV
