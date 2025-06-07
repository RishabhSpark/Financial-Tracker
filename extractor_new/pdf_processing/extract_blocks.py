import fitz
from typing import List

def extract_blocks(pdf_path: str) -> List[str]:
    """
    Extracts layout-aware text blocks from a PDF using PyMuPDF.

    Args:
        pdf_path (str): Path to the PDF file.

    Returns:
        List[str]: A list of extracted text blocks, each representing a logical section or paragraph from the PDF.
    """
    doc = fitz.open(pdf_path)
    all_blocks = []

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for b in blocks:
            if "lines" in b:
                lines = []
                for l in b["lines"]:
                    spans = [s["text"] for s in l["spans"] if s["text"].strip()]
                    if spans:
                        lines.append(" ".join(spans))
                if lines:
                    all_blocks.append("\n".join(lines))

    return all_blocks
