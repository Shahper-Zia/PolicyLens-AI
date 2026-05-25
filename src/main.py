from processor.pdf_processor import PDFProcessor
import os


if __name__ == "__main__":
    current_path = os.getcwd()
    print(current_path)

    pdf_path = "testing_21.pdf"  # Replace with your PDF file path
    processed_pdf_path = "./"  # Replace with your desired output directory

    pdf_processor = PDFProcessor(pdf_path, processed_pdf_path)
    extracted_text = pdf_processor.extract_text()
    print(extracted_text)