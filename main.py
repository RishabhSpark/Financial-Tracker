from db.crud import insert_or_replace_po
from db.database import init_db
from extractor.run_extraction import run_pipeline
from extractor.export import export_all_pos_json, export_all_csvs

from forecast_processor import run_forecast_processing

if __name__ == "__main__":
    init_db()

    pdf_paths = [
        "input/POs/RT Test data-1.pdf",
        "input/POs/RT Test data-2.pdf",
        "input/POs/RT Test data-3.pdf"
    ]

    print("--- Starting PDF Extraction and Database Storage ---")
    for pdf_path in pdf_paths:
        print(f"Processing PDF: {pdf_path}")
        pdf_text = run_pipeline(pdf_path)
        if pdf_text:
            insert_or_replace_po(pdf_text)
        else:
            print(
                f"Warning: No data extracted from {pdf_path}. Skipping database insertion for this file.")
    print("--- PDF Extraction and Database Storage Complete ---")

    print("\n--- Exporting Data to JSON and CSV ---")
    export_all_pos_json()
    export_all_csvs()
    print("--- Data Export Complete ---")

    print("\n--- Generating Financial Forecast ---")

    run_forecast_processing(input_json_path="./output/purchase_orders.json")
    print("--- Financial Forecast Generation Complete ---")

    print("\nAll processes finished successfully!")
