from db.crud import insert_or_replace_po
from db.database import init_db
from extractor.run_extraction import run_pipeline
from extractor.export import export_all_pos_json, export_all_csvs

if __name__ == "__main__":
    init_db()
    
    pdf_paths = [
        "input/RT Test data-1.pdf",
        "input/RT Test data-2.pdf",
        "input/RT Test data-3.pdf"
    ]
    
    for pdf_path in pdf_paths:
        pdf_text = run_pipeline(pdf_path)
        insert_or_replace_po(pdf_text)
    
    export_all_pos_json()
    export_all_csvs()