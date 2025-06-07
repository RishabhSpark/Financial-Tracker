import pdfplumber
from typing import List

def extract_tables(pdf_path: str) -> List[List[List[str]]]:
    """
    Extracts tables from a PDF using pdfplumber.

    Args:
        pdf_path (str): Path to the PDF file.

    Returns:
        List[List[List[str]]]: A list of tables, where each table is a list of rows, and each row is a list of cell values.
    """
    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            extracted = page.extract_tables()
            for table in extracted:
                tables.append(table)
    return tables
