from extractor.pdf_processing.extract_tables import extract_tables
from extractor.pdf_processing.extract_blocks import extract_blocks
from extractor.po_extractor import classify_project_payment_category
from extractor.pdf_processing.format_po import format_po_for_llm


def run_pipeline(pdf_path):
    print(f"Processing {pdf_path}...")
    blocks = extract_blocks(pdf_path)
    tables = extract_tables(pdf_path)

    formatted_po = format_po_for_llm(blocks, tables)
    
    # Classify the project payment category
    payment_category = classify_project_payment_category(formatted_po)
    print(payment_category)
    
    return payment_category