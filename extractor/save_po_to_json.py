import json
import os
from datetime import datetime
from app.schemas.po_target_schema import POFields
from app.core.logger import setup_logger

logger = setup_logger()

def save_po_to_json(po_data: POFields, output_dir: str = "output/json/") -> str:
    """
    Save the validated PO data to a timestamped JSON file.

    Args:
        po_data (POFields): The validated PO data from the LLM.
        output_dir (str): Directory where the JSON file should be saved.

    Returns:
        str: Path to the saved JSON file.
    """
    try:
        os.makedirs(output_dir, exist_ok=True)

        client_name = po_data.client_name.replace(" ", "_").lower()[:30]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"po_{client_name}_{timestamp}.json"
        file_path = os.path.join(output_dir, filename)

        with open(file_path, "w") as f:
            json.dump(po_data.model_dump(), f, indent=2)

        logger.info(f"PO data saved to: {file_path}")
        return file_path

    except Exception as e:
        logger.exception("Failed to save PO data to JSON")
        raise