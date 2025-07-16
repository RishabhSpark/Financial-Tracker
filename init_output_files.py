import json
from pathlib import Path
import openpyxl
from db.database import init_db as original_init_db
from typing import Literal

BASE_OUTPUT_DIR = Path('output')
DATABASE_DIR = BASE_OUTPUT_DIR / "database"
DB_FILE_PATH = DATABASE_DIR / "po_database.db"
def create_or_empty_file(filepath: Path, filetype: Literal['csv', 'json', 'xlsx'] = 'csv') -> None:
    """
    Creates or empties a file at the given filepath, ensuring its parent directories exist.

    Args:
        filepath (Path): The path to the file to create or empty.
        filetype (Literal['csv', 'json', 'xlsx']): The type of file to create.
                                                   Defaults to 'csv'.
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)

    if filepath.exists():
        filepath.unlink() 
    if filetype == 'json':
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump([], f)
    elif filetype == 'xlsx':
        wb = openpyxl.Workbook()
        wb.save(filepath)
    else:  
        
        filepath.touch() 

def init_db() -> None:
    """
    Initializes the database. If the database file exists, it is deleted first to ensure a fresh start.
    """
    db_path = DB_FILE_PATH
    if db_path.exists():
        db_path.unlink() # Use pathlib's unlink
    # Now call the original initialization logic
    original_init_db()


if __name__ == "__main__":
    init_db()

    base_output_dir = Path('output')
    processed_output_dir = base_output_dir / "processed"
    llm_output_dir = base_output_dir / "LLM output"

    base_output_dir.mkdir(parents=True, exist_ok=True) # Ensures 'output' exists
    processed_output_dir.mkdir(parents=True, exist_ok=True) # Ensures 'output/processed' exists
    llm_output_dir.mkdir(parents=True, exist_ok=True) # Ensures 'output/LLM output' exists

    print("Initializing output files and directories...")


    # Files for 'output/processed/'
    create_or_empty_file(processed_output_dir / 'forecast_output.csv', filetype='csv')
    create_or_empty_file(processed_output_dir / 'forecast_pivot.xlsx', filetype='xlsx')

    # Files for 'output/LLM output/'
    create_or_empty_file(llm_output_dir / 'distributed.csv', filetype='csv')
    create_or_empty_file(llm_output_dir / 'milestones.csv', filetype='csv')
    create_or_empty_file(llm_output_dir / 'periodic.csv', filetype='csv')
    create_or_empty_file(llm_output_dir / 'purchase_orders.csv', filetype='csv')
    create_or_empty_file(llm_output_dir / 'purchase_orders.json', filetype='json')

    print("All output files and directories initialized successfully.")