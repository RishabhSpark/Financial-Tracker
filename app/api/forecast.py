from fastapi import APIRouter
from services.forecast import forecast_table
from schemas.po_target_schema import POFields  # Pydantic schema

router = APIRouter()

@router.post("/forecast")
def generate_forecast(po: PurchaseOrder):
    df = forecast_table(po.dict())
    return df.to_dict(orient="records")

