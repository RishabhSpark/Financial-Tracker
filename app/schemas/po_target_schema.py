from typing import Optional, Union, List, Literal
from pydantic import BaseModel, field_validator, root_validator, ValidationError
from datetime import datetime


def parse_dd_mm_yyyy(date_str: Optional[str]) -> Optional[str]:
    """Parse a date string into 'DD-MM-YYYY' format."""
    if not date_str:
        return None

    accepted_formats = [
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d/%m/%y",
        "%Y-%m-%d",
        "%d-%m-%y",
        "%d %b %Y",
        "%d %B %Y",
        "%d %b, %Y",
        "%d %B, %Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%m/%d/%Y",  # e.g. US format
    ]

    clean_date_str = date_str.replace(",", "").strip().title()

    for fmt in accepted_formats:
        try:
            return datetime.strptime(clean_date_str, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue

    raise ValueError(f"Invalid date format, expected DD-MM-YYYY: {date_str}")


# ------------------ Sub-models ------------------

class MilestoneItem(BaseModel):
    name: str
    percentage: float
    expected_date: Optional[str] = None

    @field_validator("expected_date", mode="before")
    @classmethod
    def validate_expected_date(cls, v):
        return parse_dd_mm_yyyy(v) if v else None


class DistributedPayment(BaseModel):
    date: str
    amount: float

    @field_validator("date", mode="before")
    @classmethod
    def validate_date(cls, v):
        return parse_dd_mm_yyyy(v)


class PeriodicSchedule(BaseModel):
    frequency: Optional[str] = "monthly"
    distribution: Optional[List[float]] = []


# ------------------ Main PO Fields ------------------

class POFields(BaseModel):
    client_name: Optional[str]
    po_id: Optional[str]
    amount: Union[str, float, int]
    status: Optional[str]
    payment_terms: Optional[int]
    payment_type: Optional[Literal["milestone", "distributed", "periodic"]]
    start_date: Optional[str]
    end_date: Optional[str]
    duration_months: Optional[Union[int, str]] = None
    payment_schedule: Optional[
        Union[List[MilestoneItem], List[DistributedPayment], PeriodicSchedule]
    ]

    # ------------------ Validators ------------------

    @field_validator("amount", mode="before")
    @classmethod
    def normalize_amount(cls, v):
        if v is None:
            return None
        return float(v.replace(",", "")) if isinstance(v, str) else float(v)

    @field_validator("payment_terms", mode="before")
    @classmethod
    def normalize_payment_terms(cls, v):
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def validate_dates(cls, v):
        return parse_dd_mm_yyyy(v) if v else None

    @field_validator("duration_months", mode="before")
    @classmethod
    def normalize_duration(cls, v):
        if v is None or str(v).strip().lower() == "null":
            return None
        if isinstance(v, str):
            try:
                return int(float(v))
            except ValueError:
                return None
        if isinstance(v, float):
            return int(v)
        return v

    @root_validator(pre=True)
    @classmethod
    def validate_payment_schedule_by_type(cls, values):
        pt = values.get("payment_type")
        ps = values.get("payment_schedule")

        try:
            if pt == "milestone":
                values["payment_schedule"] = [MilestoneItem(**item) for item in ps or []]
            elif pt == "distributed":
                values["payment_schedule"] = [DistributedPayment(**item) for item in ps or []]
            elif pt == "periodic":
                values["payment_schedule"] = PeriodicSchedule(**(ps or {}))
            else:
                values["payment_schedule"] = None
        except Exception as e:
            raise ValueError(f"Invalid payment_schedule structure for type '{pt}': {e}")

        return values
