import asyncio
from datetime import datetime
from extractor_new.pdf_processing.extract_blocks import extract_blocks
from extractor_new.pdf_processing.extract_tables import extract_tables
from extractor_new.po_extractor import classify_project_payment_category
from extractor_new.pdf_processing.format_po import format_po_for_llm
from db.database import AsyncSessionLocal
from db.crud import create_purchase_order
import json

def parse_date(date_str):
    """Parse a date string like 'DD-MM-YYYY' or 'YYYY-MM-DD' to datetime.date or return None."""
    if not date_str:
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    # If all fail, return None or raise error as needed
    return None

async def process_and_store_po(pdf_path: str):
    text_blocks = extract_blocks(pdf_path)
    tables = extract_tables(pdf_path)
    po_text = format_po_for_llm(text_blocks, tables)
    
    po_data = classify_project_payment_category(po_text)
    print(json.dumps(po_data, indent=2))

    # Convert dates to datetime.date objects (important for DB insert)
    if po_data.get("start_date"):
        po_data["start_date"] = parse_date(po_data["start_date"])
    if po_data.get("end_date"):
        po_data["end_date"] = parse_date(po_data["end_date"])

    # Ensure keys expected by your model exist (example for missing optional keys)
    po_data.setdefault("milestones", None)
    po_data.setdefault("payment_schedule", None)
    po_data.setdefault("payment_frequency", None)

    async with AsyncSessionLocal() as session:
        po = await create_purchase_order(session, po_data)
        print(f"Saved PO with po_id={po.po_id}")

if __name__ == "__main__":
    pdf_paths = [
        "input/RT Test data-1.pdf",
        "input/RT Test data-2.pdf",
        "input/RT Test data-3.pdf"
    ]

    async def main():
        for pdf in pdf_paths:
            await process_and_store_po(pdf)

    asyncio.run(main())
