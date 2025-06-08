from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import os

Base = declarative_base()
DATABASE_URL = "sqlite:///po_database.db"

engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(bind=engine)

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True, index=True)
    po_id = Column(String, unique=True, index=True)
    client_name = Column(String)
    amount = Column(Float)
    status = Column(String)
    payment_terms = Column(Integer)
    payment_type = Column(String)
    start_date = Column(String)
    end_date = Column(String)
    duration_months = Column(Integer)
    payment_frequency = Column(Integer, nullable=True)

    milestones = relationship("Milestone", cascade="all, delete-orphan", backref="purchase_order")
    payment_schedule = relationship("PaymentSchedule", cascade="all, delete-orphan", backref="purchase_order")

class Milestone(Base):
    __tablename__ = "milestones"
    id = Column(Integer, primary_key=True)
    po_id = Column(String, ForeignKey("purchase_orders.po_id"))
    milestone_name = Column(String)
    milestone_description = Column(String, nullable=True)
    milestone_due_date = Column(String, nullable=True)
    milestone_percentage = Column(Float)

class PaymentSchedule(Base):
    __tablename__ = "payment_schedule"
    id = Column(Integer, primary_key=True)
    po_id = Column(String, ForeignKey("purchase_orders.po_id"))
    payment_date = Column(String)
    payment_amount = Column(Float)
    payment_description = Column(String, nullable=True)

def init_db():
    if not os.path.exists("po_database.db"):
        Base.metadata.create_all(bind=engine)
