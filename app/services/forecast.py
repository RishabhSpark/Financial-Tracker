from datetime import datetime
import pandas as pd
import re
from typing import Dict, Any
from dateutil.parser import parse

def classify_payment_type(data: Dict) -> str:
    return data.get("payment_type", "unknown")

def get_monthly_inflow(data: Dict[str, Any]) -> Dict[str, float]:
    """
    Calculates monthly inflow based on payment data, handling distributed,
    fixed, even, milestone, and periodic payment types.

    Args:
        data (Dict): A dictionary containing payment details.
                     Expected keys vary by 'payment_type':
                     - "start_date" (str, optional): Project start date (e.g., "DD-MM-YYYY").
                     - "end_date" (str, optional): Project end date (e.g., "DD-MM-YYYY").
                     - "amount" (float): Total contract amount.
                     - "payment_terms" (int): Payment delay in days.
                     - "payment_type" (str): Type of payment ("distributed", "fixed", "even", "milestone", "periodic").
                     - "payment_schedule" (List[Dict], for "distributed" type):
                       List of dictionaries, each with "payment_date" and "payment_amount".
                     - "milestones" (List[Dict], for "milestone" type):
                       List of dictionaries, each with "milestone_due_date" (or None) and "milestone_percentage".
                     - "payment_schedule" (Dict, for "periodic" type):
                       Dictionary with "payment_frequency" (int) in months.

    Returns:
        Dict[str, float]: A dictionary where keys are "YYYY-MM" and values are the
                          total inflow for that month.
    """
    # Parse dates and handle potential missing keys
    start = pd.to_datetime(data.get("start_date"), format="%d-%m-%Y", errors='coerce') if data.get("start_date") else None
    end = pd.to_datetime(data.get("end_date"), format="%d-%m-%Y", errors='coerce') if data.get("end_date") else None
    
    total = float(data.get("amount", 0.0))
    pay_type = data.get("payment_type", "unknown").lower() # Ensure lowercase for comparison

    delay_days = int(data.get("payment_terms", 0))

    inflow = {}

    if pay_type == "distributed":
        payment_schedule = data.get("payment_schedule", [])

        for division in payment_schedule:
            amount = 0.0
            if "payment_amount" in division:
                amount = float(division["payment_amount"])
            elif "payment_percent" in division:
                percent = float(str(division["payment_percent"]).strip('%'))
                amount = total * percent / 100
            else:
                continue

            pay_date = None
            if "payment_date" in division and division["payment_date"] not in ["None", None, ""]:
                try:
                    pay_date = pd.to_datetime(division["payment_date"], format="%d-%m-%Y")
                except ValueError:
                    print(f"Warning: Could not parse date '{division['payment_date']}' in distributed payment schedule. Skipping this entry.")
                    continue
            
            if pay_date:
                effective_date = pay_date + pd.Timedelta(days=delay_days)
                month = (effective_date.replace(day=1)).strftime("%Y-%m")
                inflow[month] = inflow.get(month, 0.0) + amount

    elif pay_type == "milestone":
        milestones = data.get("milestones", [])
        num_milestones = len(milestones)

        if not milestones: # No milestones to process
            return inflow

        # Calculate inferred dates if due dates are not explicitly provided
        inferred_dates = [None] * num_milestones
        if start and end and num_milestones > 0:
            # Distribute dates evenly across the project duration if no explicit due dates
            inferred_dates = pd.date_range(start=start, end=end, periods=num_milestones).tolist()
        elif start and num_milestones > 0:
            # If only start, distribute quarterly or based on milestone count
            # This is a simple fallback. More complex logic might be needed based on specific rules.
            for i in range(num_milestones):
                inferred_dates[i] = start + pd.DateOffset(months=(i * (12 // num_milestones))) if num_milestones <= 12 else start + pd.DateOffset(days=i * ((end - start).days / num_milestones if start and end else 30))


        for i, milestone in enumerate(milestones):
            amount = 0.0
            if "milestone_percentage" in milestone:
                percent = float(str(milestone["milestone_percentage"]).strip('%'))
                amount = total * percent / 100
            else:
                continue # Skip if no percentage specified

            pay_date = None
            if "milestone_due_date" in milestone and milestone["milestone_due_date"] not in ["None", None, ""]:
                try:
                    pay_date = pd.to_datetime(milestone["milestone_due_date"], format="%d-%m-%Y")
                except ValueError:
                    print(f"Warning: Could not parse date '{milestone['milestone_due_date']}' for milestone '{milestone.get('milestone_name', 'Unnamed')}'. Using inferred date.")
                    # Fallback to inferred date if parsing fails
                    pay_date = inferred_dates[i] if i < len(inferred_dates) else None
            else:
                # Use inferred date if milestone_due_date is "None" or missing
                pay_date = inferred_dates[i] if i < len(inferred_dates) else None
            
            if pay_date:
                effective_date = pay_date + pd.Timedelta(days=delay_days)
                month = (effective_date.replace(day=1)).strftime("%Y-%m")
                inflow[month] = inflow.get(month, 0.0) + amount
            else:
                print(f"Warning: No valid date found for milestone '{milestone.get('milestone_name', 'Unnamed')}'. Skipping this milestone.")


    elif pay_type == "fixed":
        # This part of the logic assumes that if 'payment_schedule' is a string, it's the old format.
        # If 'fixed' will now ALSO use the list of dicts format like 'distributed' or 'milestone',
        # you might need to unify the parsing of 'payment_schedule' list for all list-based types.
        # For now, it keeps the old string parsing if it receives a string.
        schedule_data = data.get("payment_schedule")
        if isinstance(schedule_data, str) and schedule_data:
            payments = schedule_data.split(";")
            for entry in payments:
                if ":$" in entry:
                    try:
                        date_str, amount_str = entry.strip().split(":$")
                        date = pd.to_datetime(date_str, format="%d-%m-%Y")
                        date += pd.Timedelta(days=delay_days)
                        month = date.strftime("%Y-%m")
                        inflow[month] = inflow.get(month, 0.0) + float(amount_str)
                    except ValueError:
                        print(f"Warning: Could not parse fixed payment entry '{entry}'. Skipping.")
                        continue
        else: # Handle case where payment_schedule might be the new list of dicts for fixed
            # If fixed payments are also provided as a list of dicts, you might need a similar
            # loop to the 'distributed' type here. For example:
            if isinstance(schedule_data, list):
                print("Note: 'fixed' payment type received a list for 'payment_schedule'. Processing as if 'distributed'.")
                # You might copy/paste the distributed logic here or refactor into a helper.
                for item in schedule_data:
                    amount = 0.0
                    if "payment_amount" in item: # Assuming similar keys
                        amount = float(item["payment_amount"])
                    elif "payment_percent" in item:
                        percent = float(str(item["payment_percent"]).strip('%'))
                        amount = total * percent / 100
                    else:
                        continue
                    pay_date = None
                    if "payment_date" in item and item["payment_date"] not in ["None", None, ""]:
                        try:
                            pay_date = pd.to_datetime(item["payment_date"], format="%d-%m-%Y")
                        except ValueError:
                            print(f"Warning: Could not parse date '{item['payment_date']}' in fixed payment schedule. Skipping this entry.")
                            continue
                    if pay_date:
                        effective_date = pay_date + pd.Timedelta(days=delay_days)
                        month = (effective_date.replace(day=1)).strftime("%Y-%m")
                        inflow[month] = inflow.get(month, 0.0) + amount
            else:
                print(f"Warning: 'fixed' payment type expected string or list for 'payment_schedule' but got {type(schedule_data)}. Skipping 'fixed' calculation.")


    elif pay_type == "even":
        if start and end:
            months = pd.date_range(start=start, end=end, freq='MS')
            if len(months) > 0:
                monthly_amount = total / len(months)
                for date in months:
                    date += pd.Timedelta(days=delay_days)
                    month = date.strftime("%Y-%m")
                    inflow[month] = inflow.get(month, 0.0) + monthly_amount
            else:
                print("Warning: 'even' payment type, but start/end dates result in no months. Inflow will be empty for this type.")
        else:
            print("Warning: 'even' payment type requires valid 'start_date' and 'end_date'. Skipping 'even' calculation.")

    elif pay_type == "periodic":
        payment_schedule = data.get("payment_schedule", {})
        payment_frequency = payment_schedule.get("payment_frequency", 1) 

        if start and end and payment_frequency > 0:
            # Generate the *scheduled* payment dates first
            scheduled_dates = []
            current_scheduled_date = start
            while current_scheduled_date <= end:
                scheduled_dates.append(current_scheduled_date)
                current_scheduled_date += pd.DateOffset(months=payment_frequency)

            if not scheduled_dates:
                print("Warning: No scheduled dates generated for 'periodic' payment. No payments will be scheduled.")
                return inflow

            amount_per_period = total / len(scheduled_dates)

            for scheduled_date in scheduled_dates:
                effective_date = scheduled_date + pd.Timedelta(days=delay_days)
                
                # --- NEW LOGIC FOR SHIFTING MONTH ---
                if effective_date.day >= 25: # If payment lands on or after the 25th, push to next month
                    adjusted_date_for_month = effective_date + pd.DateOffset(months=1)
                    month = (adjusted_date_for_month.replace(day=1)).strftime("%Y-%m")
                else:
                    month = (effective_date.replace(day=1)).strftime("%Y-%m")
                # --- END NEW LOGIC ---

                inflow[month] = inflow.get(month, 0.0) + amount_per_period
            
        else:
            print("Warning: 'periodic' payment type requires valid 'start_date', 'end_date', and 'payment_frequency' > 0. Skipping 'periodic' calculation.")
    else:
        raise ValueError(f"Unsupported or missing payment type: {pay_type}")

    return inflow


def forecast_table(data: Dict) -> pd.DataFrame:
    inflow = get_monthly_inflow(data)
    po_number = data['po_id']
    client_name= data['client_name']
    pay_type = classify_payment_type(data)

    rows = [
        {
            "Client Name": client_name,
            "Month": month,
            "Inflow (USD)": amount,
            "PO No": po_number,
            
        }
        for month, amount in inflow.items()
    ]

    return pd.DataFrame(rows)