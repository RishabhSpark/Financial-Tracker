from dotenv import load_dotenv
from app.core.logger import setup_logger
from extractor.llm_client import get_llm, get_prompt, get_json_parser

logger = setup_logger()
load_dotenv()

DISTRIBUTED_PROMPT = """
You are an assistant that extracts structured data from a Distributed project payment Purchase Order.

Extract these common fields exactly:
- client_name (string)
- po_id (string)
- amount (number in USD, no currency symbols)
- status (exactly one of [\"Confirmed\", \"Quote Sent\", \"Under Discussion\", \"Negotiation\"])
- payment_terms (integer, days)
- payment_type (exactly \"distributed\")
- start_date (DD-MM-YYYY; if only MM-YYYY given, treat as 1st day of month)
- end_date (DD-MM-YYYY; if only MM-YYYY given, treat as last day of month)
- duration_months (float or null; do NOT calculate from dates, only explicit mention)

For distributed payments, also extract:
- payment_schedule: a list of payment entries, each with:
    - payment_date (DD-MM-YYYY)
    - payment_amount (number, USD)
    - payment_description (optional string)

Return only a valid JSON object.

Purchase Order text:
\"\"\"
{po_text}
\"\"\"
"""

def extract_distributed_payment_details(po_text: str) -> dict:
    logger.info("Starting extraction of distributed payment details from PO text.")
    llm = get_llm()
    prompt = get_prompt(DISTRIBUTED_PROMPT)
    parser = get_json_parser()
    chain = prompt | llm | parser

    try:
        result = chain.invoke({"po_text": po_text})
        logger.info("Successfully extracted distributed payment details from PO text.")
        return result
    except Exception as e:
        logger.error("Failed to extract or parse JSON from LLM response.")
        logger.debug(str(e))
        raise e
