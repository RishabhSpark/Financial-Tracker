"""
Copyright (C) 2024 promto-c
Permission Notice:
- You are free to use, copy, modify, and distribute this software for any purpose.
- No restrictions are imposed on the use of this software.
- You do not need to give credit or include this notice in your work.
- Use at your own risk.
- This software is provided "AS IS" without any warranty, either expressed or implied.
"""
# Type Checking Imports
# ---------------------
from typing import List, Tuple

# Standard Library Imports
# ------------------------
import sqlite3


def export_schema(db_path: str, output_file: str) -> None:
    """Exports the schema of the given SQLite database to a SQL file.
    Args:
        db_path: The path to the SQLite database file.
        output_file: The path to the output file where the schema will be saved.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    with open(output_file, 'w') as f:
        for line in conn.iterdump():
            f.write(f'{line}\n')
    
    conn.close()

def convert_to_dbml(db_path: str, dbml_output: str) -> None:
    """Converts the schema of the given SQLite database to DBML format and saves it to a file.
    Args:
        db_path: The path to the SQLite database file.
        dbml_output: The path to the output file where the DBML will be saved.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all user-defined tables, excluding SQLite internal tables
    tables: List[Tuple[str]] = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    ).fetchall()
    dbml_lines: List[str] = []

    for table in tables:
        table_name: str = table[0]
        dbml_lines.append(f"Table {table_name} {{")
        columns: List[Tuple[int, str, str, int, str, int]] = cursor.execute(f"PRAGMA table_info({table_name});").fetchall()
        
        for column in columns:
            col_name: str = column[1]
            col_type: str = column[2]
            col_pk: str = "pk" if column[5] else ""
            col_def: str = f"{col_name} {col_type} {col_pk}".strip()
            dbml_lines.append(f"  {col_def}")
        
        dbml_lines.append("}")
    
    # Add relationships
    for table in tables:
        table_name: str = table[0]
        foreign_keys: List[Tuple[int, int, str, str, str, str, str, str, str, str]] = cursor.execute(f"PRAGMA foreign_key_list({table_name});").fetchall()
        
        for fk in foreign_keys:
            fk_table: str = fk[2]
            fk_from: str = fk[3]
            fk_to: str = fk[4]
            dbml_lines.append(f"Ref: {table_name}.{fk_from} > {fk_table}.{fk_to}")

    conn.close()
    
    with open(dbml_output, 'w') as f:
        f.write('\n'.join(dbml_lines))

if __name__ == '__main__':
    # Export SQLite schema
    export_schema('po_database.db', 'schema.sql')
