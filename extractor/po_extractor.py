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
You are a document extraction AI assisting the finance team.

Given the text of a Purchase Order (PO), extract and return ONLY valid JSON with the following fields:

---
Required fields:
- client_name: Client name as a string.
- po_id: Purchase Order ID as a string.
- amount: Total amount in USD as a number (no currency symbols).
- status: One of ["Confirmed", "Quote Sent", "Under Discussion", "Negotiation"] exactly. Assess the document and take a verdict.
- payment_terms: Number of days for payment terms as an integer.
- payment_type: One of ["milestone", "distributed", "periodic"] exactly. Milestone are those where milestones are mentioned or when divisions are mentioned in percentages. Distributed are those where the payment is distributed among different dates and they will be mentioned in the document. Periodic are those where only the start date and end date are mentioned, and sometimes how frequently the payment will happen is mentioned.
- start_date: Date in DD-MM-YYYY format. If only MM-YYYY is given, treat as 1st day of that month.
- end_date: Date in DD-MM-YYYY format. If only MM-YYYY is given, treat as last day of that month.
- duration_months: Duration in months if mentioned explicitly, else null. Should be a float. Do NOT calculate from dates.
- payment_schedule: 
    For "milestone": An array of objects, each with:
        - name: milestone name (string). If not specified name them "initial", "milestone_1", "milestone_2", ...; or if initial not mentioned then start from "milestone_1", "milestone_2", ...
        - percentage: payment percentage as decimal (e.g., 0.2 for 20%)
        - expected_date: optional, payment date in DD-MM-YYYY format if available.
    For "distributed": An array of objects, each with:
        - date: payment date in DD-MM-YYYY format
        - amount: payment amount as a number
    For "periodic": An object with:
        - frequency: payment frequency as string (e.g., "monthly", "quarterly")
        - distribution: array of decimals representing percentage distribution, summing to 1.

---
Rules:
1. Always return ONLY valid JSON. Do NOT add markdown, comments, explanations, or any extra text.
2. Use double quotes for all JSON keys and string values.
3. If a required field is missing or cannot be found, return null for that field.
4. For optional fields, omit them if the information is not present.
5. Dates must be strictly formatted as "DD-MM-YYYY". If incomplete date info is given (only month-year), convert according to the rules above.
6. For payment percentages and distributions, use decimals (e.g., 0.25 for 25%), NOT percentages or strings.
7. When naming milestones without explicit names, follow the sequence: "initial" first if present, then "milestone_1", "milestone_2", and so forth. If "initial" not mentioned then go with "milestone_1", "milestone_2", ...
9. Payment status must exactly match one of the allowed strings.
10. Validate that numeric fields like amount, payment_terms, percentage are proper numbers, not strings.

Return ONLY the JSON.

Here is the Purchase Order text:

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
