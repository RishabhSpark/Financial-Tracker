from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Float, Date, JSON
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True, index=True)
    client_name = Column(String, nullable=False)
    po_id = Column(String, unique=True, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    payment_terms = Column(Integer, nullable=False)
    payment_type = Column(String, nullable=False)  # milestone / distributed / periodic
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    duration_months = Column(Float, nullable=True)

    # JSON fields for each payment type details
    milestones = Column(JSONB, nullable=True)    # list of milestone dicts
    payment_schedule = Column(JSONB, nullable=True)  # for distributed payments
    payment_frequency = Column(Integer, nullable=True)  # months, for periodic