import google.generativeai as genai
import os
from app.schemas.po_target_schema import POFields
import json
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel("gemini-1.5-flash")

def extract_po_details_from_text(text: str) -> POFields:
    """
    Uses Gemini to extract structured PO data from unstructured text.
    """

    prompt = f"""
You are a document extraction AI.

Given a Purchase Order text, extract the following fields and return ONLY valid JSON:

---
Required fields:
- client_name
- po_id
- amount
- status
- payment_terms
- payment_type: One of ["milestone", "distributed", "periodic"]
- start_date
- end_date
- payment_divisions:
    {{
        "payment_1": {{ "date": "...", "amount": "..." }},
        "payment_2": {{ "date": "...", "amount": "..." }},
        ...
    }}
---

Respond with JSON only, nothing else.

Here is the PO text:

{text}
"""

    response = model.generate_content(prompt)
    response_text = response.text.strip()

    # Try extracting valid JSON from response
    try:
        # If Gemini returns markdown block, extract the JSON inside
        if response_text.startswith("```json"):
            response_text = response_text.strip("```json").strip("```").strip()
        data = json.loads(response_text)
        validated = POFields(**data)
        return validated
    except Exception as e:
        raise ValueError(f"Gemini returned invalid JSON or failed validation: {e}")
