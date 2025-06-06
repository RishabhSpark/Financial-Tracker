from typing import List

def format_table_as_markdown(table: List[List[str]]) -> str:
    """
    Formats a 2D table into a markdown-style string for LLM-friendly parsing.

    Args:
        table (List[List[str]]): A table represented as a list of rows (each row is a list of strings).

    Returns:
        str: A string representation of the table in markdown format.
    """
    if not table or not table[0]:
        return ""

    header = "| " + " | ".join(table[0]) + " |"
    separator = "| " + " | ".join(["---"] * len(table[0])) + " |"
    rows = ["| " + " | ".join(row) + " |" for row in table[1:]]

    return "\n".join([header, separator] + rows)