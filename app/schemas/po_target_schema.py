from pydantic import BaseModel, field_validator
from typing import Optional, Dict, Union


class PaymentDetail(BaseModel):
    date: Optional[str] = None
    amount: Union[str, int]

    @field_validator("amount", mode="before")
    def normalize_amount(cls, v):
        return str(v) if v is not None else None

    @field_validator("date", mode="before")
    def normalize_date(cls, v):
        return str(v) if v is not None else None


class POFields(BaseModel):
    client_name: Optional[str]
    po_id: Optional[str]
    amount: Union[str, int]
    status: Optional[str]
    payment_terms: Optional[str]
    payment_type: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]
    duration: Optional[str] = None
    payment_divisions: Optional[Dict[str, PaymentDetail]]

    @field_validator("amount", mode="before")
    def normalize_main_amount(cls, v):
        return str(v) if v is not None else None