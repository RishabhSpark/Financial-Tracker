import os
import json
import pandas as pd
from pathlib import Path
import openpyxl
from app.services.forecast import forecast_table
from app.core.logger import setup_logger

logger = setup_logger()

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

    logger.info("Running Forecast Processor")
    
    try:
        with open(file_path, 'r') as f:
            po_data_list = json.load(f)
        logger.info(f"JSON data loaded successfully from {input_json_path}.")

        for po_data in po_data_list:
            if isinstance(po_data, dict):
                df = forecast_table(po_data)
                all_forecast_dfs.append(df)
            else:
                logger.warning(
                    f"Warning: Expected dictionary for PO data but got {type(po_data)}. Skipping entry.")

    except FileNotFoundError:
        logger.error(
            f"The file at path {file_path} was not found. Cannot perform forecasting.")
        return
    except json.JSONDecodeError:
        logger.error(
            f"Could not decode JSON from {file_path}. Is it valid JSON? Cannot perform forecasting.")
        return
    except Exception as e:
        logger.error(f"An unexpected error occurred during forecasting: {e}")
        return

    # Consolidate DataFrame creation
    if not all_forecast_dfs:
        combined_df = pd.DataFrame()
    else:
        combined_df = pd.concat(all_forecast_dfs, ignore_index=True)

    if combined_df.empty:
        logger.warning("No forecast data available to process. Skipping CSV and Excel output.")
        return

    # Round "Inflow (USD)" to 2 decimal places
    if "Inflow (USD)" in combined_df.columns:
        combined_df["Inflow (USD)"] = pd.to_numeric(combined_df["Inflow (USD)"], errors='coerce')
        combined_df["Inflow (USD)"] = combined_df["Inflow (USD)"].round(2)
        combined_df["Inflow (USD)"] = combined_df["Inflow (USD)"].fillna(0.0)

    # Standardize 'Month' column to 'YYYY-MM' string
    if 'Month' in combined_df.columns:
        try:
            datetime_months = pd.to_datetime(combined_df['Month'], errors='coerce')
            combined_df['Month'] = datetime_months.dt.strftime('%Y-%m')
            combined_df.dropna(subset=['Month'], inplace=True)
        except Exception as e:
            logger.warning(f"Could not standardize 'Month' column format: {e}. Proceeding with existing format.")
            if not pd.api.types.is_string_dtype(combined_df['Month']):
                combined_df['Month'] = combined_df['Month'].astype(str)

    if "Client Name" in combined_df.columns:
        combined_df["Client Name"] = combined_df["Client Name"].astype(str).str.strip()
    if "PO No" in combined_df.columns:
        combined_df["PO No"] = combined_df["PO No"].astype(str).str.strip()

    # Remove duplicate rows after standardization
    if not combined_df.empty:
        combined_df.drop_duplicates(inplace=True, keep='last')

    logger.info("Processed Forecast Table.")
    combined_df.to_csv(output_csv_path, index=False, float_format='%.2f')
    logger.info(f"Saved forecast table to '{output_csv_path}'")

    # Pivot Table Logic
    if combined_df.empty or 'Month' not in combined_df.columns or combined_df['Month'].isnull().all():
        logger.warning("No valid data for pivot table generation. Skipping pivot.")
    else:
        try:
            # Use 'Month' as datetime for min/max range calculation
            month_as_datetime = pd.to_datetime(combined_df['Month'], format='%Y-%m', errors='coerce')
            month_as_datetime.dropna(inplace=True)

            if month_as_datetime.empty:
                logger.error("No valid 'Month' data in 'YYYY-MM' format for pivot table. Skipping pivot generation.")
            else:
                min_month = month_as_datetime.min()
                max_month = month_as_datetime.max()
                all_months_for_pivot = pd.date_range(min_month, max_month, freq='MS').strftime('%Y-%m')

                pivot = combined_df.pivot_table(
                    index=["Client Name", "PO No", "Project Owner", "Status"],
                    columns="Month",
                    values="Inflow (USD)",
                    aggfunc="sum",
                    fill_value=0.0
                )

                # Ensure all months are present as columns
                pivot = pivot.reindex(columns=all_months_for_pivot, fill_value=0.0)
                pivot.reset_index(inplace=True) 

                if not pivot.empty:
                    if 'S.No' in pivot.columns:
                        pivot = pivot.drop(columns=['S.No'])
                    month_cols = [col for col in pivot.columns if col not in ['Client Name', 'PO No', 'Project Owner', 'Status']]
                    new_order = ['S.No', 'Client Name', 'PO No', 'Project Owner', 'Status'] + month_cols
                    pivot.insert(0, 'S.No', range(1, 1 + len(pivot)))
                    pivot = pivot[new_order]

                # Round float columns to integer for Excel output
                for col in pivot.columns:
                    if pd.api.types.is_float_dtype(pivot[col]):
                        pivot[col] = pivot[col].round(0).astype(int)

                with pd.ExcelWriter(pivot_excel_path, engine='openpyxl') as writer:
                    pivot.to_excel(writer, index=False, sheet_name="Forecast")
                    
                    workbook = writer.book
                    worksheet = writer.sheets["Forecast"]
                    
                    s_no_offset = 1 if 'S.No' in pivot.columns else 0
                    
                    first_month_col_idx = 0
                    if 'S.No' in pivot.columns:
                        first_month_col_idx +=1 
                    if "Client Name" in pivot.columns:
                        first_month_col_idx +=1
                    if "PO No" in pivot.columns:
                        first_month_col_idx +=1
                    if "Project Owner" in pivot.columns:
                        first_month_col_idx +=1
                    if "Status" in pivot.columns:
                        first_month_col_idx +=1

                    # Apply number formatting to month columns in Excel
                    for row in worksheet.iter_rows(min_row=2,
                                                   min_col=first_month_col_idx + 1,
                                                   max_col=worksheet.max_column):
                        for cell in row:
                            if cell.value is not None:
                                try:
                                    float_val = float(cell.value)
                                    cell.number_format = '0'
                                except ValueError:
                                    pass

                logger.info(f"Saved forecast pivot to '{pivot_excel_path}'")
        except Exception as e:
            logger.error(f"Error during pivot table generation: {e}. Skipping pivot generation.")