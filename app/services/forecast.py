from datetime import datetime
import pandas as pd
import re
from typing import Dict, Any
from dateutil.parser import parse


def classify_payment_type(data: Dict) -> str:
    return data.get("payment_type", "unknown")


def parse_date_flexible(date_str):
    """
    Parse date string with multiple format support and handle incomplete entries.
    Returns pandas datetime or None if parsing fails.
    """
    if not date_str or date_str in ["None", None, "", "nan", "NaN"]:
        return None
    
    # Clean the date string
    date_str = str(date_str).strip()
    if not date_str:
        return None
    
    # Try multiple date formats
    date_formats = [
        "%d-%m-%Y",    # DD-MM-YYYY
        "%Y-%m-%d",    # YYYY-MM-DD
        "%m/%d/%Y",    # MM/DD/YYYY
        "%d/%m/%Y",    # DD/MM/YYYY
        "%Y/%m/%d",    # YYYY/MM/DD
        "%d.%m.%Y",    # DD.MM.YYYY
        "%Y.%m.%d",    # YYYY.MM.DD
    ]
    
    for fmt in date_formats:
        try:
            return pd.to_datetime(date_str, format=fmt)
        except (ValueError, TypeError):
            continue
    
    # Try pandas' flexible parser as last resort
    try:
        return pd.to_datetime(date_str, errors='coerce')
    except:
        return None


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

    start = parse_date_flexible(data.get("start_date"))
    end = parse_date_flexible(data.get("end_date"))

    total = float(data.get("amount", 0.0))
    pay_type = data.get("payment_type", "unknown").lower()

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
                pay_date = parse_date_flexible(division["payment_date"])
                if pay_date is None:
                    print(f"Warning: Could not parse date '{division['payment_date']}' in distributed payment schedule. Skipping this entry.")
                    continue

            if pay_date:
                effective_date = pay_date + pd.Timedelta(days=delay_days)
                month = (effective_date.replace(day=1)).strftime("%Y-%m")
                inflow[month] = inflow.get(month, 0.0) + amount

    elif pay_type == "milestone":
        milestones = data.get("milestones", [])
        num_milestones = len(milestones)

        if not milestones:
            return inflow

        inferred_dates = [None] * num_milestones
        if start and end and num_milestones > 0:

            inferred_dates = pd.date_range(
                start=start, end=end, periods=num_milestones).tolist()
        elif start and num_milestones > 0:

            for i in range(num_milestones):
                inferred_dates[i] = start + pd.DateOffset(months=(i * (12 // num_milestones))) if num_milestones <= 12 else start + pd.DateOffset(
                    days=i * ((end - start).days / num_milestones if start and end else 30))

        for i, milestone in enumerate(milestones):
            amount = 0.0
            if "milestone_percentage" in milestone:
                percent = float(
                    str(milestone["milestone_percentage"]).strip('%'))
                amount = total * percent / 100
            else:
                continue

            pay_date = None
            if "milestone_due_date" in milestone and milestone["milestone_due_date"] not in ["None", None, ""]:
                pay_date = parse_date_flexible(milestone["milestone_due_date"])
                if pay_date is None:
                    print(f"Warning: Could not parse date '{milestone['milestone_due_date']}' for milestone '{milestone.get('milestone_name', 'Unnamed')}'. Using inferred date.")
                    pay_date = inferred_dates[i] if i < len(inferred_dates) else None
            else:

                pay_date = inferred_dates[i] if i < len(
                    inferred_dates) else None

            if pay_date:
                effective_date = pay_date + pd.Timedelta(days=delay_days)
                month = (effective_date.replace(day=1)).strftime("%Y-%m")
                inflow[month] = inflow.get(month, 0.0) + amount
            else:
                print(
                    f"Warning: No valid date found for milestone '{milestone.get('milestone_name', 'Unnamed')}'. Skipping this milestone.")

    elif pay_type == "fixed":
        schedule_data = data.get("payment_schedule")
        if isinstance(schedule_data, str) and schedule_data:
            payments = schedule_data.split(";")
            for entry in payments:
                if ":$" in entry:
                    try:
                        date_str, amount_str = entry.strip().split(":$")
                        date = parse_date_flexible(date_str)
                        if date is None:
                            print(f"Warning: Could not parse date '{date_str}' in fixed payment entry '{entry}'. Skipping.")
                            continue
                        date += pd.Timedelta(days=delay_days)
                        month = date.strftime("%Y-%m")
                        inflow[month] = inflow.get(month, 0.0) + float(amount_str)
                    except ValueError:
                        print(
                            f"Warning: Could not parse fixed payment entry '{entry}'. Skipping.")
                        continue
        else:
            if isinstance(schedule_data, list):
                print(
                    "Note: 'fixed' payment type received a list for 'payment_schedule'. Processing as if 'distributed'.")

                for item in schedule_data:
                    amount = 0.0
                    if "payment_amount" in item:
                        amount = float(item["payment_amount"])
                    elif "payment_percent" in item:
                        percent = float(
                            str(item["payment_percent"]).strip('%'))
                        amount = total * percent / 100
                    else:
                        continue
                    pay_date = None
                    if "payment_date" in item and item["payment_date"] not in ["None", None, ""]:
                        pay_date = parse_date_flexible(item["payment_date"])
                        if pay_date is None:
                            print(f"Warning: Could not parse date '{item['payment_date']}' in fixed payment schedule. Skipping this entry.")
                            continue
                    if pay_date:
                        effective_date = pay_date + \
                            pd.Timedelta(days=delay_days)
                        month = (effective_date.replace(
                            day=1)).strftime("%Y-%m")
                        inflow[month] = inflow.get(month, 0.0) + amount
            else:
                print(
                    f"Warning: 'fixed' payment type expected string or list for 'payment_schedule' but got {type(schedule_data)}. Skipping 'fixed' calculation.")

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
                print(
                    "Warning: 'even' payment type, but start/end dates result in no months. Inflow will be empty for this type.")
        else:
            print("Warning: 'even' payment type requires valid 'start_date' and 'end_date'. Skipping 'even' calculation.")

    elif pay_type == "periodic":
        payment_schedule = data.get("payment_schedule", {})
        payment_frequency = payment_schedule.get("payment_frequency", 1)

        if start and end and payment_frequency > 0:

            scheduled_dates = []
            current_scheduled_date = start
            while current_scheduled_date <= end:
                scheduled_dates.append(current_scheduled_date)
                current_scheduled_date += pd.DateOffset(
                    months=payment_frequency)

            if not scheduled_dates:
                print(
                    "Warning: No scheduled dates generated for 'periodic' payment. No payments will be scheduled.")
                return inflow

            amount_per_period = total / len(scheduled_dates)

            for scheduled_date in scheduled_dates:
                effective_date = scheduled_date + pd.Timedelta(days=delay_days)

                if effective_date.day >= 25:
                    adjusted_date_for_month = effective_date + \
                        pd.DateOffset(months=1)
                    month = (adjusted_date_for_month.replace(
                        day=1)).strftime("%Y-%m")
                else:
                    month = (effective_date.replace(day=1)).strftime("%Y-%m")

                inflow[month] = inflow.get(month, 0.0) + amount_per_period

        else:
            print("Warning: 'periodic' payment type requires valid 'start_date', 'end_date', and 'payment_frequency' > 0. Skipping 'periodic' calculation.")
    else:
        raise ValueError(f"Unsupported or missing payment type: {pay_type}")

    return inflow


def forecast_table(data: Dict) -> pd.DataFrame:
    # Validate and clean the data first
    cleaned_data = validate_and_clean_data(data)
    if cleaned_data is None:
        return pd.DataFrame()  # Return empty DataFrame for invalid data
    
    inflow = get_monthly_inflow(cleaned_data)
    po_number = cleaned_data['po_id']
    client_name = cleaned_data['client_name']
    pay_type = classify_payment_type(cleaned_data)
    project_owner = cleaned_data.get('project_owner') or "-"
    
    # Normalize status to one of the allowed values
    raw_status = cleaned_data.get('status', '').strip().lower()
    if raw_status in ['confirmed']:
        status = "Confirmed"
    elif raw_status in ['unconfirmed']:
        status = "Unconfirmed"
    else:
        status = "unspecified"
    
    rows = [
        {
            "Client Name": client_name,
            "Month": month,
            "Inflow (USD)": amount,
            "PO No": po_number,
            "Project Owner": project_owner,
            "Status": status,
        }
        for month, amount in inflow.items()
    ]

    return pd.DataFrame(rows)

def validate_and_clean_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and clean PO data, removing incomplete or invalid entries.
    Returns cleaned data or None if data is too incomplete to process.
    """
    if not isinstance(data, dict):
        return None
    
    # Check for minimum required fields
    required_fields = ['po_id', 'client_name', 'amount', 'payment_type']
    for field in required_fields:
        if not data.get(field) or str(data.get(field)).strip() in ['', 'None', 'nan', 'NaN']:
            print(f"Warning: Missing or empty required field '{field}' in PO data. Skipping this entry.")
            return None
    
    # Clean and validate amount
    try:
        amount = float(data.get('amount', 0))
        if amount <= 0:
            print(f"Warning: Invalid amount '{data.get('amount')}' for PO {data.get('po_id')}. Skipping this entry.")
            return None
        data['amount'] = amount
    except (ValueError, TypeError):
        print(f"Warning: Could not parse amount '{data.get('amount')}' for PO {data.get('po_id')}. Skipping this entry.")
        return None
    
    # Clean string fields
    string_fields = ['po_id', 'client_name', 'payment_type', 'status', 'project_owner']
    for field in string_fields:
        if field in data and data[field] is not None:
            data[field] = str(data[field]).strip()
    
    # Validate payment_type
    valid_payment_types = ['distributed', 'milestone', 'fixed', 'even', 'periodic']
    payment_type = data.get('payment_type', '').lower().strip()
    if payment_type not in valid_payment_types:
        print(f"Warning: Invalid payment_type '{data.get('payment_type')}' for PO {data.get('po_id')}. Skipping this entry.")
        return None
    data['payment_type'] = payment_type
    
    # Clean payment terms
    try:
        payment_terms = int(data.get('payment_terms', 0))
        data['payment_terms'] = max(0, payment_terms)  # Ensure non-negative
    except (ValueError, TypeError):
        data['payment_terms'] = 0
    
    # Clean milestones if present
    if payment_type == 'milestone' and 'milestones' in data:
        clean_milestones = []
        for milestone in data.get('milestones', []):
            if isinstance(milestone, dict) and 'milestone_percentage' in milestone:
                try:
                    percentage = float(str(milestone['milestone_percentage']).strip('%'))
                    if percentage > 0:  # Only include milestones with positive percentage
                        milestone['milestone_percentage'] = percentage
                        clean_milestones.append(milestone)
                except (ValueError, TypeError):
                    continue
        data['milestones'] = clean_milestones
        
        if not clean_milestones:
            print(f"Warning: No valid milestones found for milestone payment type in PO {data.get('po_id')}. Skipping this entry.")
            return None
    
    # Clean payment schedule if present
    if payment_type == 'distributed' and 'payment_schedule' in data:
        clean_schedule = []
        for payment in data.get('payment_schedule', []):
            if isinstance(payment, dict):
                # Check if payment has either amount or percentage
                has_amount = 'payment_amount' in payment and payment['payment_amount'] not in [None, '', 'None']
                has_percent = 'payment_percent' in payment and payment['payment_percent'] not in [None, '', 'None']
                
                if has_amount or has_percent:
                    try:
                        if has_amount:
                            amount = float(payment['payment_amount'])
                            if amount > 0:
                                clean_schedule.append(payment)
                        elif has_percent:
                            percent = float(str(payment['payment_percent']).strip('%'))
                            if percent > 0:
                                clean_schedule.append(payment)
                    except (ValueError, TypeError):
                        continue
        data['payment_schedule'] = clean_schedule
        
        if not clean_schedule:
            print(f"Warning: No valid payment schedule found for distributed payment type in PO {data.get('po_id')}. Skipping this entry.")
            return None
    
    return data
