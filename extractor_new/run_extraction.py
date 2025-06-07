from extractor_new.pdf_processing.extract_blocks import extract_blocks
from extractor_new.pdf_processing.extract_tables import extract_tables
from extractor_new.po_extractor import classify_project_payment_category
from extractor_new.pdf_processing.format_po import format_po_for_llm
# from extractor_new.save_po_to_json import save_po_to_json
import json

if __name__ == "__main__":
    
    pdf_path = ["input/RT Test data-1.pdf",
                "input/RT Test data-2.pdf",
                "input/RT Test data-3.pdf"]
                
    for pdf in pdf_path:
        text_blocks = extract_blocks(pdf)
        tables = extract_tables(pdf)

        po_text = format_po_for_llm(text_blocks, tables)
        
        po_data = classify_project_payment_category(po_text)
        print(json.dumps(po_data, indent=2))
    
    # save_po_to_json(po_data)