from typing import List
import fitz

def extract_text_from_pdf(pdf_path: str) -> List[str]:
    """
    Extracts text from each page of a PDF.

    Args:
        pdf_path (str): Path to the PDF file.

    Returns:
        List[str]: List of text strings for each page.
    """
    text_pages = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text = page.get_text()
            text_pages.append(text)
    return text_pages