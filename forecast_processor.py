import os
import json
import pandas as pd
from pathlib import Path
import openpyxl
from app.services.forecast import forecast_table 

def run_forecast_processing(input_json_path: str = "./output/purchase_orders.json",
                            output_csv_path: str = "forecast_output.csv",
                            pivot_excel_path: str = "forecast_pivot.xlsx"):
    """
    Loads PO data from JSON, generates a forecast table,
    and saves it to CSV and a pivot table to Excel.

    Args:
        input_json_path (str): Path to the input JSON file containing PO data.
        output_csv_path (str): Path to the output CSV file for the forecast table.
        pivot_excel_path (str): Path to the output Excel file for the pivot table.
    """
    file_path = Path(input_json_path)
    all_forecast_dfs = []

    try:
        with open(file_path, 'r') as f:
            po_data_list = json.load(f)
        print(f"JSON data loaded successfully from {input_json_path}.")
        
        for po_data in po_data_list:
          
            if isinstance(po_data, dict):
                df = forecast_table(po_data)
                all_forecast_dfs.append(df)
            else:
                print(f"Warning: Expected dictionary for PO data but got {type(po_data)}. Skipping entry.")

    except FileNotFoundError:
        print(f"Error: The file at path {file_path} was not found. Cannot perform forecasting.")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}. Is it valid JSON? Cannot perform forecasting.")
        return
    except Exception as e:
        print(f"An unexpected error occurred during forecasting: {e}")
        return

    if all_forecast_dfs:
        combined_df = pd.concat(all_forecast_dfs, ignore_index=True)

        combined_df.drop_duplicates(subset=["Client Name", "Month", "Inflow (USD)", "PO No"], keep="last", inplace=True)
    else:
        print("No forecast data generated. Skipping CSV and Excel output.")
        return 

    print("\n📊 Forecast Table:")
    print(combined_df)

   
    if os.path.exists(output_csv_path):
        existing_df = pd.read_csv(output_csv_path)
        combined_df = pd.concat([existing_df, combined_df], ignore_index=True)
        combined_df.drop_duplicates(subset=["Client Name", "Month", "Inflow (USD)", "PO No"], keep="last", inplace=True)

    combined_df.to_csv(output_csv_path, index=False)
    print(f"\n✅ Saved forecast table to '{output_csv_path}'")

   
    pivot = combined_df.pivot_table(
        index=["Client Name", "PO No"],      
        columns="Month",                     
        values="Inflow (USD)",               
        aggfunc="sum",                       
        fill_value=0                         
    ).reset_index()

    with pd.ExcelWriter(pivot_excel_path, engine='openpyxl') as writer:
        pivot.to_excel(writer, index=False, sheet_name="Forecast")
    print(f"\n✅ Saved forecast pivot to '{pivot_excel_path}'")