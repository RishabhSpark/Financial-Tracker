from extractor.pdf_processing.extract_blocks import extract_blocks
from extractor.pdf_processing.extract_tables import extract_tables
from extractor.pdf_processing.format_table_as_markdown import format_table_as_markdown
from extractor.po_extractor import extract_po_details_from_text
from extractor.pdf_processing.format_po import format_po_for_llm
from extractor.save_po_to_json import save_po_to_json

def run_pipeline(pdf_path: str) -> None:
    """
    Runs the full pipeline:
    - Extracts layout-aware text blocks from the PDF.
    - Extracts tables and formats them for LLMs.
    - Prints all extracted content.

    Args:
        pdf_path (str): Path to the PDF file.
    """
    text_blocks = extract_blocks(pdf_path)
    tables = extract_tables(pdf_path)

    po_text = format_po_for_llm(text_blocks, tables)
    # print("TEXT BLOCKS:\n")
    # for block in text_blocks:
    #     print(block)
    #     print("\n---\n")

    # print("EXTRACTED TABLES (Markdown Format):\n")
    # for table in tables:
    #     print(format_table_as_markdown(table))
    #     print("\n====================\n")
        
        
    po_data = extract_po_details_from_text(po_text)
    print(po_data.model_dump_json(indent=2))
    
    save_po_to_json(po_data)