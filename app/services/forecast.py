import pandas as pd
from typing import Dict, Any, List, Optional, Union
from dateutil.parser import parse
from app.core.logger import setup_logger

logger = setup_logger()

def classify_payment_type(data: Dict[str, Any]) -> str:
    """Classify payment type from data dict."""
    return data.get("payment_type", "unknown")

def parse_date_flexible(date_str: Optional[Union[str, float, int]]) -> Optional[pd.Timestamp]:
    """
    Parse date string with multiple format support and handle incomplete entries.
    Returns pandas Timestamp or None if parsing fails.
    """
    if not date_str or str(date_str) in ["None", "", "nan", "NaN"]:
        return None

    date_str = str(date_str).strip()
    if not date_str:
        return None

    date_formats = [
        "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y",
        "%Y/%m/%d", "%d.%m.%Y", "%Y.%m.%d"
    ]
    for fmt in date_formats:
        try:
            return pd.to_datetime(date_str, format=fmt)
        except (ValueError, TypeError):
            continue
    try:
        return pd.to_datetime(date_str, errors='coerce')
    except Exception:
        return None

def get_monthly_inflow(data: Dict[str, Any]) -> Dict[str, float]:
    """
    Calculates monthly inflow based on payment data, handling distributed,
    fixed, even, milestone, and periodic payment types.
    """
    start = parse_date_flexible(data.get("start_date"))
    end = parse_date_flexible(data.get("end_date"))
    total = float(data.get("amount", 0.0))
    pay_type = data.get("payment_type", "unknown").lower()
    delay_days = int(data.get("payment_terms", 0))
    inflow: Dict[str, float] = {}

    if pay_type == "distributed":
        payment_schedule: List[Dict[str, Any]] = data.get("payment_schedule", [])
        for division in payment_schedule:
            amount = 0.0
            if "payment_amount" in division:
                try:
                    amount = float(division["payment_amount"])
                except (ValueError, TypeError):
                    continue
            elif "payment_percent" in division:
                try:
                    percent = float(str(division["payment_percent"]).strip('%'))
                    amount = total * percent / 100
                except (ValueError, TypeError):
                    continue
            else:
                continue

            pay_date = None
            if "payment_date" in division and division["payment_date"] not in ["None", None, ""]:
                pay_date = parse_date_flexible(division["payment_date"])
                if pay_date is None:
                    logger.warning(f"Could not parse date '{division['payment_date']}' in distributed payment schedule. Skipping this entry.")
                    continue

            if pay_date:
                effective_date = pay_date + pd.Timedelta(days=delay_days)
                month = (effective_date.replace(day=1)).strftime("%Y-%m")
                inflow[month] = inflow.get(month, 0.0) + amount

    elif pay_type == "milestone":
        milestones: List[Dict[str, Any]] = data.get("milestones", [])
        num_milestones = len(milestones)
        if not milestones:
            return inflow

        inferred_dates: List[Optional[pd.Timestamp]] = [None] * num_milestones
        if start and end and num_milestones > 0:
            inferred_dates = pd.date_range(start=start, end=end, periods=num_milestones).tolist()
        elif start and num_milestones > 0:
            for i in range(num_milestones):
                inferred_dates[i] = start + pd.DateOffset(months=(i * (12 // num_milestones))) if num_milestones <= 12 else start + pd.DateOffset(
                    days=i * ((end - start).days / num_milestones if start and end else 30))

        for i, milestone in enumerate(milestones):
            amount = 0.0
            if "milestone_percentage" in milestone:
                try:
                    percent = float(str(milestone["milestone_percentage"]).strip('%'))
                    amount = total * percent / 100
                except (ValueError, TypeError):
                    continue
            else:
                continue

            pay_date = None
            if "milestone_due_date" in milestone and milestone["milestone_due_date"] not in ["None", None, ""]:
                pay_date = parse_date_flexible(milestone["milestone_due_date"])
                if pay_date is None:
                    logger.warning(f"Could not parse date '{milestone['milestone_due_date']}' for milestone '{milestone.get('milestone_name', 'Unnamed')}'. Using inferred date.")
                    pay_date = inferred_dates[i] if i < len(inferred_dates) else None
            else:
                pay_date = inferred_dates[i] if i < len(inferred_dates) else None

            if pay_date:
                effective_date = pay_date + pd.Timedelta(days=delay_days)
                month = (effective_date.replace(day=1)).strftime("%Y-%m")
                inflow[month] = inflow.get(month, 0.0) + amount
            else:
                logger.warning(f"No valid date found for milestone '{milestone.get('milestone_name', 'Unnamed')}'. Skipping this milestone.")

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
                            logger.warning(f"Could not parse date '{date_str}' in fixed payment entry '{entry}'. Skipping.")
                            continue
                        date += pd.Timedelta(days=delay_days)
                        month = date.strftime("%Y-%m")
                        inflow[month] = inflow.get(month, 0.0) + float(amount_str)
                    except ValueError:
                        logger.warning(f"Could not parse fixed payment entry '{entry}'. Skipping.")
                        continue
        else:
            if isinstance(schedule_data, list):
                logger.info("Note: 'fixed' payment type received a list for 'payment_schedule'. Processing as if 'distributed'.")
                for item in schedule_data:
                    amount = 0.0
                    if "payment_amount" in item:
                        try:
                            amount = float(item["payment_amount"])
                        except (ValueError, TypeError):
                            continue
                    elif "payment_percent" in item:
                        try:
                            percent = float(str(item["payment_percent"]).strip('%'))
                            amount = total * percent / 100
                        except (ValueError, TypeError):
                            continue
                    else:
                        continue
                    pay_date = None
                    if "payment_date" in item and item["payment_date"] not in ["None", None, ""]:
                        pay_date = parse_date_flexible(item["payment_date"])
                        if pay_date is None:
                            logger.warning(f"Could not parse date '{item['payment_date']}' in fixed payment schedule. Skipping this entry.")
                            continue
                    if pay_date:
                        effective_date = pay_date + pd.Timedelta(days=delay_days)
                        month = (effective_date.replace(day=1)).strftime("%Y-%m")
                        inflow[month] = inflow.get(month, 0.0) + amount
            else:
                logger.warning(f"'fixed' payment type expected string or list for 'payment_schedule' but got {type(schedule_data)}. Skipping 'fixed' calculation.")

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
                logger.warning("Warning: 'even' payment type, but start/end dates result in no months. Inflow will be empty for this type.")
        else:
            logger.warning("Warning: 'even' payment type requires valid 'start_date' and 'end_date'. Skipping 'even' calculation.")

    elif pay_type == "periodic":
        payment_schedule = data.get("payment_schedule", {})
        payment_frequency = payment_schedule.get("payment_frequency", 1) if isinstance(payment_schedule, dict) else 1

        if start and end and payment_frequency > 0:
            scheduled_dates: List[pd.Timestamp] = []
            current_scheduled_date = start
            while current_scheduled_date <= end:
                scheduled_dates.append(current_scheduled_date)
                current_scheduled_date += pd.DateOffset(months=payment_frequency)

            if not scheduled_dates:
                logger.warning("No scheduled dates generated for 'periodic' payment. No payments will be scheduled.")
                return inflow

            amount_per_period = total / len(scheduled_dates)
            for scheduled_date in scheduled_dates:
                effective_date = scheduled_date + pd.Timedelta(days=delay_days)
                if effective_date.day >= 25:
                    adjusted_date_for_month = effective_date + pd.DateOffset(months=1)
                    month = (adjusted_date_for_month.replace(day=1)).strftime("%Y-%m")
                else:
                    month = (effective_date.replace(day=1)).strftime("%Y-%m")
                inflow[month] = inflow.get(month, 0.0) + amount_per_period
        else:
            logger.warning("Warning: 'periodic' payment type requires valid 'start_date', 'end_date', and 'payment_frequency' > 0. Skipping 'periodic' calculation.")
    else:
        raise ValueError(f"Unsupported or missing payment type: {pay_type}")

    return inflow

def forecast_table(data: Dict[str, Any]) -> pd.DataFrame:
    """
    Generate a forecast table DataFrame from PO data.
    """
    cleaned_data = validate_and_clean_data(data)
    if cleaned_data is None:
        return pd.DataFrame()
    inflow = get_monthly_inflow(cleaned_data)
    po_number = cleaned_data['po_id']
    client_name = cleaned_data['client_name']
    pay_type = classify_payment_type(cleaned_data)
    project_owner = cleaned_data.get('project_owner') or "-"
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

def validate_and_clean_data(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Validate and clean PO data, removing incomplete or invalid entries.
    Returns cleaned data or None if data is too incomplete to process.
    """
    if not isinstance(data, dict):
        logger.warning("Input data is not a dictionary. Skipping entry.")
        return None

    required_fields = ['po_id', 'client_name', 'amount', 'payment_type']
    for field in required_fields:
        if not data.get(field) or str(data.get(field)).strip() in ['', 'None', 'nan', 'NaN']:
            logger.warning(f"Missing or empty required field '{field}' in PO data. Skipping this entry.")
            return None

    try:
        amount = float(data.get('amount', 0))
        if amount <= 0:
            logger.warning(f"Invalid amount '{data.get('amount')}' for PO {data.get('po_id')}. Skipping this entry.")
            return None
        data['amount'] = amount
    except (ValueError, TypeError):
        logger.warning(f"Could not parse amount '{data.get('amount')}' for PO {data.get('po_id')}. Skipping this entry.")
        return None

    string_fields = ['po_id', 'client_name', 'payment_type', 'status', 'project_owner']
    for field in string_fields:
        if field in data and data[field] is not None:
            data[field] = str(data[field]).strip()

    valid_payment_types = ['distributed', 'milestone', 'fixed', 'even', 'periodic']
    payment_type = data.get('payment_type', '').lower().strip()
    if payment_type not in valid_payment_types:
        logger.warning(f"Invalid payment_type '{data.get('payment_type')}' for PO {data.get('po_id')}. Skipping this entry.")
        return None
    data['payment_type'] = payment_type

    try:
        payment_terms = int(data.get('payment_terms', 0))
        data['payment_terms'] = max(0, payment_terms)
    except (ValueError, TypeError):
        logger.warning(f"Invalid payment_terms '{data.get('payment_terms')}' for PO {data.get('po_id')}. Defaulting to 0.")
        data['payment_terms'] = 0

    if payment_type == 'milestone' and 'milestones' in data:
        clean_milestones: List[Dict[str, Any]] = []
        for milestone in data.get('milestones', []):
            if isinstance(milestone, dict) and 'milestone_percentage' in milestone:
                try:
                    percentage = float(str(milestone['milestone_percentage']).strip('%'))
                    if percentage > 0:
                        milestone['milestone_percentage'] = percentage
                        clean_milestones.append(milestone)
                    else:
                        logger.warning(f"Milestone with non-positive percentage '{milestone['milestone_percentage']}' in PO {data.get('po_id')}. Skipping milestone.")
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse milestone_percentage '{milestone.get('milestone_percentage')}' in PO {data.get('po_id')}. Skipping milestone.")
                    continue
            else:
                logger.warning(f"Milestone missing 'milestone_percentage' or not a dict in PO {data.get('po_id')}. Skipping milestone.")
        data['milestones'] = clean_milestones
        if not clean_milestones:
            logger.warning(f"No valid milestones found for milestone payment type in PO {data.get('po_id')}. Skipping this entry.")
            return None

    if payment_type == 'distributed' and 'payment_schedule' in data:
        clean_schedule: List[Dict[str, Any]] = []
        for payment in data.get('payment_schedule', []):
            if isinstance(payment, dict):
                has_amount = 'payment_amount' in payment and payment['payment_amount'] not in [None, '', 'None']
                has_percent = 'payment_percent' in payment and payment['payment_percent'] not in [None, '', 'None']
                if has_amount or has_percent:
                    try:
                        if has_amount:
                            amount = float(payment['payment_amount'])
                            if amount > 0:
                                clean_schedule.append(payment)
                            else:
                                logger.warning(f"Payment with non-positive amount '{payment['payment_amount']}' in PO {data.get('po_id')}. Skipping payment.")
                        elif has_percent:
                            percent = float(str(payment['payment_percent']).strip('%'))
                            if percent > 0:
                                clean_schedule.append(payment)
                            else:
                                logger.warning(f"Payment with non-positive percent '{payment['payment_percent']}' in PO {data.get('po_id')}. Skipping payment.")
                    except (ValueError, TypeError):
                        logger.warning(f"Could not parse payment_amount/payment_percent in PO {data.get('po_id')}. Skipping payment.")
                        continue
                else:
                    logger.warning(f"Payment missing amount/percent in PO {data.get('po_id')}. Skipping payment.")
            else:
                logger.warning(f"Payment schedule entry not a dict in PO {data.get('po_id')}. Skipping payment.")
        data['payment_schedule'] = clean_schedule
        if not clean_schedule:
            logger.warning(f"No valid payment schedule found for distributed payment type in PO {data.get('po_id')}. Skipping this entry.")
            return None

    return data