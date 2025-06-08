import os
from dotenv import load_dotenv
import google.generativeai as genai

from extractor.extract_distributed_details import extract_distributed_payment_details
from extractor.extract_milestone_details import extract_milestone_payment_details
from extractor.extract_periodic_details import extract_periodic_payment_details

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not set in environment variables.")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

def classify_project_payment_category(po_text: str) -> str:
    """
    Uses Gemini to extract structured PO data from unstructured text.
    """

    prompt = f"""
You are a classification assistant.

Given the following purchase order text, classify it into one of these project payment categories:
- Periodic: Periodic are those where only the start date and end date are mentioned, and sometimes how frequently the payment will happen is mentioned.
- Distributed: Distributed are those where the payment is distributed among different dates and they will be mentioned in the document.
- Milestone: Milestone are those where milestones are mentioned or when divisions are mentioned in percentages.

Return only the exact category name: Periodic, Distributed, or Milestone based.

Purchase Order text:
\"\"\"
{po_text}
\"\"\"
Category:
"""

    classification_resp = model.generate_content(prompt)
    payment_type = classification_resp.text.strip().lower()

    print(payment_type)
    
    if payment_type not in {"periodic", "distributed", "milestone"}:
        raise ValueError(f"Unexpected payment_type returned: {payment_type}")

    if payment_type == "periodic":
        return extract_periodic_payment_details(po_text)
    elif payment_type == "distributed":
        return extract_distributed_payment_details(po_text)
    else:
        return extract_milestone_payment_details(po_text)
