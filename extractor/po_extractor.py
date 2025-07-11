from extractor.extract_distributed_details import extract_distributed_payment_details
from extractor.extract_milestone_details import extract_milestone_payment_details
from extractor.extract_periodic_details import extract_periodic_payment_details
from app.core.logger import setup_logger
from extractor.llm_client import get_llm, get_prompt

logger = setup_logger()

CLASSIFY_PROMPT = """
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

def classify_project_payment_category(po_text: str) -> str:
    logger.info("Classifying project payment category using LLM.")
    llm = get_llm()
    prompt = get_prompt(CLASSIFY_PROMPT)
    chain = prompt | llm
    try:
        classification_resp = chain.invoke({"po_text": po_text})
        if hasattr(classification_resp, "content"):
            payment_type = classification_resp.content.strip().lower()
        else:
            payment_type = str(classification_resp).strip().lower()
        logger.info(f"LLM classified payment_type as: {payment_type}")
    except Exception as e:
        logger.error(f"Failed to classify payment type: {e}")
        raise

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
