import json
import os
import re
from dotenv import load_dotenv
import google.generativeai as genai
from app.core.logger import setup_logger

logger = setup_logger()

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY not set in environment variables.")
    raise ValueError("GEMINI_API_KEY not set in environment variables.")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

def extract_distributed_payment_details(po_text: str) -> dict:
    logger.info("Starting extraction of distributed payment details from PO text.")
    prompt = f"""
You are an assistant that extracts structured data from a Distributed project payment Purchase Order.

Extract these common fields exactly:
- client_name (string)
- po_id (string)
- amount (number in USD, no currency symbols)
- status (exactly one of ["Confirmed", "Quote Sent", "Under Discussion", "Negotiation"])
- payment_terms (integer, days)
- payment_type (exactly "distributed")
- start_date (DD-MM-YYYY; if only MM-YYYY given, treat as 1st day of month)
- end_date (DD-MM-YYYY; if only MM-YYYY given, treat as last day of month)
- duration_months (float or null; do NOT calculate from dates, only explicit mention)

For distributed payments, also extract:
- payment_schedule: a list of payment entries, each with:
    - payment_date (DD-MM-YYYY)
    - payment_amount (number, USD)
    - payment_description (optional string)

Return only a valid JSON object inside markdown code block, like this:

```json
{{ ... }}

Purchase Order text:
\"\"\"
{po_text}
\"\"\"
"""
    logger.debug("Sending prompt to Gemini model.")
    response = model.generate_content(prompt)

    raw_response = response.candidates[0].content.parts[0].text.strip()
    logger.debug("Received response from Gemini model.")

    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_response, re.DOTALL)
    if not match:
        logger.error("Gemini response did not contain valid JSON block.")
        logger.debug(f"Raw Gemini response: {raw_response}")
        raise ValueError("Gemini response did not contain valid JSON block")

    json_str = match.group(1)

    try:
        result = json.loads(json_str)
        logger.info("Successfully extracted distributed payment details from PO text.")
        return result
    except json.JSONDecodeError as e:
        logger.error("Failed to parse JSON from Gemini response.")
        logger.debug(f"Raw JSON that failed parsing: {json_str}")
        raise e