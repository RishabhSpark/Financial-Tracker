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
        new_data_df = pd.DataFrame()
    else:
        new_data_df = pd.concat(all_forecast_dfs, ignore_index=True)

    # Load existing data if available and combine
    if os.path.exists(output_csv_path):
        try:
            existing_df = pd.read_csv(output_csv_path)
            # Clean existing_df
            if "Unnamed: 0" in existing_df.columns:
                existing_df.drop(columns=["Unnamed: 0"], inplace=True)
            if 'S.No' in existing_df.columns:
                existing_df.drop(columns=['S.No'], inplace=True)
            
            frames_to_concat = []
            if not existing_df.empty:
                frames_to_concat.append(existing_df)
            if not new_data_df.empty:
                frames_to_concat.append(new_data_df)
            
            if frames_to_concat:
                combined_df = pd.concat(frames_to_concat, ignore_index=True)
            else:
                combined_df = pd.DataFrame() # Empty if both are empty
        except pd.errors.EmptyDataError:
            print(f"Warning: Existing CSV file '{output_csv_path}' is empty. Using new data if available.")
            combined_df = new_data_df
        except Exception as e:
            print(f"Warning: Error reading or processing existing CSV '{output_csv_path}': {e}. Using new data if available.")
            combined_df = new_data_df
    else:
        combined_df = new_data_df

    if combined_df.empty:
        print("No forecast data available to process. Skipping CSV and Excel output.")
        return

    # Round "Inflow (USD)" to 2 decimal places
    if "Inflow (USD)" in combined_df.columns:
        combined_df["Inflow (USD)"] = pd.to_numeric(combined_df["Inflow (USD)"], errors='coerce')
        combined_df["Inflow (USD)"] = combined_df["Inflow (USD)"].round(2)
        combined_df["Inflow (USD)"] = combined_df["Inflow (USD)"].fillna(0) # Fill NaNs that might result

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

    print("\\n📊 Processed Forecast Table:")
    combined_df.to_csv(output_csv_path, index=False)
    print(f"\\n✅ Saved forecast table to '{output_csv_path}'")

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
                    index=["Client Name", "PO No"],
                    columns="Month", # Uses the 'YYYY-MM' string 'Month' column
                    values="Inflow (USD)",
                    aggfunc="sum",
                    fill_value=0 
                )

                pivot = pivot.reindex(columns=all_months_for_pivot, fill_value=0)
                pivot.reset_index(inplace=True) 

                if not pivot.empty:
                    pivot.insert(0, 'S.No', range(1, 1 + len(pivot)))

                with pd.ExcelWriter(pivot_excel_path, engine='openpyxl') as writer:
                    pivot.to_excel(writer, index=False, sheet_name="Forecast")
                print(f"\\n✅ Saved forecast pivot to '{pivot_excel_path}'")
        except Exception as e:
            print(f"Error during pivot table generation: {e}. Skipping pivot generation.")