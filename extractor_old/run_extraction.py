from extractor.pdf_processing.extract_tables import extract_tables
from extractor.pdf_processing.extract_blocks import extract_blocks
from extractor.po_extractor import classify_project_payment_category
from extractor.pdf_processing.format_po import format_po_for_llm
from app.core.logger import setup_logger

logger = setup_logger()


def run_pipeline(pdf_path):
    logger.info(f"Starting pipeline for {pdf_path}...")
    print(f"Processing {pdf_path}...")

    try:
        blocks = extract_blocks(pdf_path)
        logger.info(f"Extracted {len(blocks)} text blocks from PDF.")
    except Exception as e:
        logger.error(f"Failed to extract text blocks: {e}")
        raise

    try:
        tables = extract_tables(pdf_path)
        logger.info(f"Extracted {len(tables)} tables from PDF.")
    except Exception as e:
        logger.error(f"Failed to extract tables: {e}")
        raise

    try:
        formatted_po = format_po_for_llm(blocks, tables)
        logger.info("Formatted PO for LLM input.")
    except Exception as e:
        logger.error(f"Failed to format PO for LLM: {e}")
        raise

    # Classify the project payment category
    try:
        logger.info("Classifying project payment category.")
        payment_category = classify_project_payment_category(formatted_po)
        logger.info(f"Classification result: {payment_category}")
        print(payment_category)
    except Exception as e:
        logger.error(f"Failed to classify project payment category: {e}")
        raise

    logger.info("Pipeline completed successfully.")
    return payment_category