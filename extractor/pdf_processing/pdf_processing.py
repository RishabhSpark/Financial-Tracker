from typing import List
import fitz
from app.core.logger import setup_logger

logger = setup_logger()

def extract_text_from_pdf(pdf_path: str) -> List[str]:
    """
    Extracts text from each page of a PDF.

    Args:
        pdf_path (str): Path to the PDF file.

    Returns:
        List[str]: List of text strings for each page.
    """
    logger.info(f"Opening PDF file for text extraction: {pdf_path}")
    text_pages = []
    try:
        with fitz.open(pdf_path) as doc:
            logger.info(f"Number of pages in PDF: {len(doc)}")
            for page_num, page in enumerate(doc, start=1):
                logger.info(f"Extracting text from page {page_num}")
                try:
                    text = page.get_text()
                    text_pages.append(text)
                    logger.debug(f"Extracted text from page {page_num} (length: {len(text)})")
                except Exception as e:
                    logger.error(f"Failed to extract text from page {page_num}: {e}")
    except Exception as e:
        logger.error(f"Failed to open PDF file '{pdf_path}': {e}")
        raise
    logger.info(f"Extracted text from {len(text_pages)} pages.")
    return text_pages