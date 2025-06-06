from typing import List

def format_po_for_llm(text_blocks: list[str], tables: list[list[list[str]]]) -> str:
    """
    Format extracted text blocks and tables into a clean plain-text string
    suitable for input to an LLM.

    Args:
        text_blocks: List of text blocks extracted from the PDF.
        tables: List of tables, where each table is a list of rows,
                and each row is a list of cell strings.

    Returns:
        A single formatted string combining all text and tables for LLM consumption.
    """
    # Join all text blocks separated by double newlines for readability
    formatted_text = "\n\n".join(text_blocks)

    # Format each table into a readable plain text table
    formatted_tables = ""
    for idx, table in enumerate(tables, start=1):
        # Convert each row (list of cells) into tab-separated strings
        table_rows = ["\t".join(map(str, row)) for row in table]
        # Join rows with newlines
        table_str = "\n".join(table_rows)
        formatted_tables += f"\n\nTable {idx}:\n{table_str}"

    # Combine text blocks and tables
    return formatted_text + formatted_tables
