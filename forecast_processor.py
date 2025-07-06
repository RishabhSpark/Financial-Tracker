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
                print(
                    f"Warning: Expected dictionary for PO data but got {type(po_data)}. Skipping entry.")

    except FileNotFoundError:
        print(
            f"Error: The file at path {file_path} was not found. Cannot perform forecasting.")
        return
    except json.JSONDecodeError:
        print(
            f"Error: Could not decode JSON from {file_path}. Is it valid JSON? Cannot perform forecasting.")
        return
    except Exception as e:
        print(f"An unexpected error occurred during forecasting: {e}")
        return

    # Consolidate DataFrame creation
    if not all_forecast_dfs:
        combined_df = pd.DataFrame()
    else:
        combined_df = pd.concat(all_forecast_dfs, ignore_index=True)

    if combined_df.empty:
        print("No forecast data available to process. Skipping CSV and Excel output.")
        return

    # Round "Inflow (USD)" to 2 decimal places
    if "Inflow (USD)" in combined_df.columns:
        combined_df["Inflow (USD)"] = pd.to_numeric(combined_df["Inflow (USD)"], errors='coerce')
        combined_df["Inflow (USD)"] = combined_df["Inflow (USD)"].round(2)
        combined_df["Inflow (USD)"] = combined_df["Inflow (USD)"].fillna(0.0) # Ensure float zero

    # Ensure 'Month' column is string 'YYYY-MM' for CSV and pivot
    if 'Month' in combined_df.columns:
        # Attempt to convert to datetime and then format, to standardize
        try:
            # Convert to datetime objects first (handles various input string formats if possible)
            datetime_months = pd.to_datetime(combined_df['Month'], errors='coerce')
            # Format to 'YYYY-MM' string
            combined_df['Month'] = datetime_months.dt.strftime('%Y-%m')
            # Drop rows where month conversion failed (NaT became NaN string or similar)
            combined_df.dropna(subset=['Month'], inplace=True)
        except Exception as e:
            print(f"Warning: Could not standardize 'Month' column format: {e}. Proceeding with existing format.")
            # As a fallback, ensure it's at least string type if not datetime-convertible
            if not pd.api.types.is_string_dtype(combined_df['Month']):
                combined_df['Month'] = combined_df['Month'].astype(str)

    # Ensure consistent types for other key columns before de-duplication
    if "Client Name" in combined_df.columns:
        combined_df["Client Name"] = combined_df["Client Name"].astype(str).str.strip()
    if "PO No" in combined_df.columns:
        combined_df["PO No"] = combined_df["PO No"].astype(str).str.strip()

    # Remove entire duplicate rows AFTER all column standardizations
    if not combined_df.empty:
        combined_df.drop_duplicates(inplace=True, keep='last')

    print("\\\\n📊 Processed Forecast Table:")
    # Save to CSV with specific float formatting
    combined_df.to_csv(output_csv_path, index=False, float_format='%.2f')
    print(f"\\\\n✅ Saved forecast table to '{output_csv_path}'")

    # --- Pivot Table Logic ---
    if combined_df.empty or 'Month' not in combined_df.columns or combined_df['Month'].isnull().all():
        print("Warning: No valid data for pivot table generation. Skipping pivot.")
    else:
        try:
            # 'Month' in combined_df is expected to be 'YYYY-MM' string here
            # Convert to datetime temporarily for min/max range calculation
            month_as_datetime = pd.to_datetime(combined_df['Month'], format='%Y-%m', errors='coerce')
            month_as_datetime.dropna(inplace=True) # Remove any rows where 'Month' wasn't 'YYYY-MM'

            if month_as_datetime.empty:
                print("Error: No valid 'Month' data in 'YYYY-MM' format for pivot table. Skipping pivot generation.")
            else:
                min_month = month_as_datetime.min()
                max_month = month_as_datetime.max()
                all_months_for_pivot = pd.date_range(min_month, max_month, freq='MS').strftime('%Y-%m')

                pivot = combined_df.pivot_table(
                    index=["Client Name", "PO No", "Project Owner"],
                    columns="Month", # Uses the 'YYYY-MM' string 'Month' column
                    values="Inflow (USD)",
                    aggfunc="sum",
                    fill_value=0.0 # Ensure float zero
                )

                pivot = pivot.reindex(columns=all_months_for_pivot, fill_value=0.0) # Ensure float zero
                pivot.reset_index(inplace=True) 

                # Reorder columns: S.No, Client Name, PO No, Project Owner, <months>
                if not pivot.empty:
                    # Remove S.No if already present to avoid duplication
                    if 'S.No' in pivot.columns:
                        pivot = pivot.drop(columns=['S.No'])
                    # Find all month columns (should be after Project Owner)
                    month_cols = [col for col in pivot.columns if col not in ['Client Name', 'PO No', 'Project Owner']]
                    new_order = ['S.No', 'Client Name', 'PO No', 'Project Owner'] + month_cols
                    pivot.insert(0, 'S.No', range(1, 1 + len(pivot)))
                    pivot = pivot[new_order]

                with pd.ExcelWriter(pivot_excel_path, engine='openpyxl') as writer:
                    pivot.to_excel(writer, index=False, sheet_name="Forecast")
                    
                    # Apply number formatting to the Excel sheet
                    workbook = writer.book
                    worksheet = writer.sheets["Forecast"]
                    
                    # Assuming 'Client Name' and 'PO No' are the first two columns,
                    # and 'S.No' is inserted at the beginning if pivot is not empty.
                    # The S.No column is at index 1 (0-based) if it exists.
                    # Client Name and PO No are after S.No or at the beginning.
                    
                    s_no_offset = 1 if 'S.No' in pivot.columns else 0
                    # Start formatting from the first month column
                    # The month columns start after 'Client Name', 'PO No', and potentially 'S.No'
                    # Typically, 'Client Name' and 'PO No' are the first two columns of the original pivot index.
                    # If S.No is added, it's at column 0. Client Name at 1, PO No at 2.
                    # So, month data starts from column index s_no_offset + 2
                    
                    first_month_col_idx = 0
                    if 'S.No' in pivot.columns:
                        first_month_col_idx +=1 
                    if "Client Name" in pivot.columns: # Should always be true after reset_index
                        first_month_col_idx +=1
                    if "PO No" in pivot.columns: # Should always be true after reset_index
                        first_month_col_idx +=1

                    for row in worksheet.iter_rows(min_row=2, # Skip header row
                                                   min_col=first_month_col_idx + 1, # 1-based indexing for openpyxl cols
                                                   max_col=worksheet.max_column):
                        for cell in row:
                            if cell.value is not None: # Check if cell is not empty
                                try:
                                    # Ensure value is float before formatting, handles cases where it might be string
                                    float_val = float(cell.value)
                                    cell.number_format = '0.00'
                                except ValueError:
                                    pass # Keep original if not a number

                print(f"\\\\n✅ Saved forecast pivot to '{pivot_excel_path}'")
        except Exception as e:
            print(f"Error during pivot table generation: {e}. Skipping pivot generation.")