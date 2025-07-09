import os
import csv
import json
from pathlib import Path
from db.database import init_db as original_init_db
from typing import Literal

def create_or_empty_file(filepath: str, filetype: Literal['csv', 'json', 'xlsx'] = 'csv') -> None:
    """
    filetype: one of 'csv', 'json', 'xlsx'
    Default is 'csv'.
    """
    # Remove file if it exists
    if os.path.exists(filepath):
        os.remove(filepath)
    if filetype == 'json':
        with open(filepath, 'w') as f:
            json.dump([], f)
    elif filetype == 'xlsx':
        import openpyxl
        wb = openpyxl.Workbook()
        wb.save(filepath)
    else:  # default to csv/empty text
        open(filepath, 'w').close()


def init_db() -> None:
    """
    Initializes the database. If the database file exists, it is deleted first to ensure a fresh start.
    """
    db_path = 'po_database.db'
    if os.path.exists(db_path):
        os.remove(db_path)
    # Now call the original initialization logic
    original_init_db()


if __name__ == "__main__":
    # Initialize the database (will empty if exists)
    init_db()

    # Ensure output directory exists
    Path('output').mkdir(exist_ok=True)

    # Create/empty required files
    create_or_empty_file('forecast_output.csv', filetype='csv')
    create_or_empty_file('forecast_pivot.xlsx', filetype='xlsx')
    create_or_empty_file('output/distributed.csv', filetype='csv')
    create_or_empty_file('output/milestones.csv', filetype='csv')
    create_or_empty_file('output/periodic.csv', filetype='csv')
    create_or_empty_file('output/purchase_orders.csv', filetype='csv')
    create_or_empty_file('output/purchase_orders.json', filetype='json')
