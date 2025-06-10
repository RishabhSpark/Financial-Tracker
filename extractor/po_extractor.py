import os
from dotenv import load_dotenv
import google.generativeai as genai

from extractor.extract_distributed_details import extract_distributed_payment_details
from extractor.extract_milestone_details import extract_milestone_payment_details
from extractor.extract_periodic_details import extract_periodic_payment_details
from app.core.logger import setup_logger

logger = setup_logger()

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY not set in environment variables.")
    raise ValueError("GEMINI_API_KEY not set in environment variables.")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

def classify_project_payment_category(po_text: str) -> str:
    """
    Uses Gemini to extract structured PO data from unstructured text.
    """
    logger.info("Classifying project payment category using Gemini model.")

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

    logger.debug("Sending classification prompt to Gemini model.")
    classification_resp = model.generate_content(prompt)
    payment_type = classification_resp.text.strip().lower()
    logger.info(f"Gemini classified payment_type as: {payment_type}")

    if payment_type not in {"periodic", "distributed", "milestone"}:
        logger.error(f"Unexpected payment_type returned: {payment_type}")
        raise ValueError(f"Unexpected payment_type returned: {payment_type}")

    logger.info(f"Extracting details for payment_type: {payment_type}")
    if payment_type == "periodic":
        return extract_periodic_payment_details(po_text)
    elif payment_type == "distributed":
        return extract_distributed_payment_details(po_text)
    else:
        return extract_milestone_payment_details(po_text)
