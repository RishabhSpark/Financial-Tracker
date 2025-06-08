import json
import os
import re
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not set in environment variables.")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

def extract_periodic_payment_details(po_text: str) -> dict:
    prompt = f"""
You are an assistant that extracts structured data from a Periodic project payment Purchase Order.

Extract these common fields exactly:
- client_name (string)
- po_id (string)
- amount (number in USD, no currency symbols)
- status (exactly one of ["Confirmed", "Quote Sent", "Under Discussion", "Negotiation"])
- payment_terms (integer, days)
- payment_type (exactly "periodic")
- start_date (DD-MM-YYYY; if only MM-YYYY given, treat as 1st day of month)
- end_date (DD-MM-YYYY; if only MM-YYYY given, treat as last day of month)
- duration_months (float or null; do NOT calculate from dates, only explicit mention)

For periodic payments, also extract:
- payment_frequency: integer number of months between payments (default to 1 if not mentioned)

Return only a valid JSON object inside markdown code block, like this:

```json
{{ ... }}

Purchase Order text:
\"\"\"
{po_text}
\"\"\"
JSON:
"""
    response = model.generate_content(prompt)

    raw_response = response.candidates[0].content.parts[0].text.strip()

    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_response, re.DOTALL)
    if not match:
        print("Raw Gemini response (not valid JSON block):")
        print(raw_response)
        raise ValueError("Gemini response did not contain valid JSON block")

    json_str = match.group(1)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print("Raw JSON that failed parsing:")
        print(json_str)
        raise e
