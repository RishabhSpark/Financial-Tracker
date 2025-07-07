import os
import re
import json
from dotenv import load_dotenv
from app.core.logger import setup_logger
from extractor.llm_client import get_llm, get_prompt, get_json_parser

logger = setup_logger()
load_dotenv()

MILESTONE_PROMPT = """
You are an assistant that extracts structured data from a Milestone-based project payment Purchase Order.

Extract these common fields exactly:
- client_name (string)
- po_id (string)
- amount (number in USD, no currency symbols)
- status (exactly one of [\"Confirmed\", \"Quote Sent\", \"Under Discussion\", \"Negotiation\"])
- payment_terms (integer, days)
- payment_type (exactly \"milestone\")
- start_date (DD-MM-YYYY; if only MM-YYYY given, treat as 1st day of month)
- end_date (DD-MM-YYYY; if only MM-YYYY given, treat as last day of month)
- duration_months (float or null; do NOT calculate from dates, only explicit mention)

For milestone payments, also extract:
- milestones: a list of milestones, each with:
    - milestone_name (string; initial should be named as \"initial\", rest should be named as \"milestone_1\", \"milestone_2\", and so on)
    - milestone_description (string, optional)
    - milestone_due_date (DD-MM-YYYY; if not mentioned leave it empty)
    - milestone_percentage (float, payment percentage)

Return only a valid JSON object.

Purchase Order text:
\"\"\"
{po_text}
\"\"\"
"""

def extract_milestone_payment_details(po_text: str) -> dict:
    logger.info("Starting extraction of milestone payment details from PO text.")
    llm = get_llm()
    prompt = get_prompt(MILESTONE_PROMPT)
    parser = get_json_parser()
    chain = prompt | llm | parser

    try:
        result = chain.invoke({"po_text": po_text})
        logger.info("Successfully extracted milestone payment details from PO text.")
        return result
    except Exception as e:
        logger.error("Failed to extract or parse JSON from LLM response.")
        logger.debug(str(e))
        raise e
