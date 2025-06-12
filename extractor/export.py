import os
import json
import pandas as pd
from sqlalchemy import create_engine
from db.database import PurchaseOrder, SessionLocal
from app.core.logger import setup_logger

logger = setup_logger()

def export_all_pos_json(output_path="output/purchase_orders.json"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    session = SessionLocal()
    logger.info("Starting export of all purchase orders to JSON.")
    
    all_pos = session.query(PurchaseOrder).all()
    export_data = []

    for po in all_pos:
        po_dict = {
            "client_name": po.client_name,
            "po_id": po.po_id,
            "amount": po.amount,
            "status": po.status,
            "payment_terms": po.payment_terms,
            "payment_type": po.payment_type,
            "start_date": po.start_date,
            "end_date": po.end_date,
            "duration_months": po.duration_months,
        }
        
        logger.debug(f"Processing PO ID: {po.po_id} with payment_type: {po.payment_type}")
        
        if po.payment_type == "milestone":
            logger.debug(f"Adding milestones for PO ID: {po.po_id}")
            po_dict["milestones"] = [
                {
                    "milestone_name": ms.milestone_name,
                    "milestone_description": ms.milestone_description,
                    "milestone_due_date": ms.milestone_due_date,
                    "milestone_percentage": ms.milestone_percentage,
                }
                for ms in po.milestones
            ]

        elif po.payment_type == "distributed":
            logger.debug(f"Adding payment schedule for distributed PO ID: {po.po_id}")
            po_dict["payment_schedule"] = [
                {
                    "payment_date": sched.payment_date,
                    "payment_amount": sched.payment_amount,
                    "payment_description": sched.payment_description,
                }
                for sched in po.payment_schedule
            ]

        elif po.payment_type == "periodic":
            logger.debug(f"Adding periodic payment info for PO ID: {po.po_id}")
            po_dict["payment_schedule"] = {"payment_frequency": po.payment_frequency}
            po_dict["duration_months"] = po.duration_months

        export_data.append(po_dict)

    session.close()
    logger.info(f"Exported {len(export_data)} purchase orders. Writing to {output_path}")
    
    with open(output_path, "w") as f:
        json.dump(export_data, f, indent=2)

    logger.info(f"Exported {len(export_data)} purchase orders with nested data to {output_path}")
    

def export_all_csvs(output_dir="output/"):
    os.makedirs(output_dir, exist_ok=True)
    engine = create_engine("sqlite:///po_database.db")

    logger.info("Starting export of all tables to CSV files.")
    
    # 1. Export purchase_orders.csv
    logger.debug("Exporting purchase_orders.csv")
    df_po = pd.read_sql("SELECT po_id, client_name, amount, status, payment_terms, payment_type, start_date, end_date, duration_months FROM purchase_orders", engine)
    df_po.to_csv(os.path.join(output_dir, "purchase_orders.csv"), index=False)

    # 2. Export milestones.csv
    logger.debug("Exporting milestones.csv")
    df_ms = pd.read_sql("SELECT po_id, milestone_name, milestone_description, milestone_due_date, milestone_percentage FROM milestones", engine)
    df_ms.to_csv(os.path.join(output_dir, "milestones.csv"), index=False)

    # 3. Export distributed.csv
    logger.debug("Exporting distributed.csv")
    df_sched = pd.read_sql("SELECT po_id, payment_date, payment_amount, payment_description FROM payment_schedule", engine)
    df_sched.to_csv(os.path.join(output_dir, "distributed.csv"), index=False)

    # 4. Export periodic.csv
    logger.debug("Exporting periodic.csv")
    df_periodic = pd.read_sql("""
        SELECT po_id, start_date, end_date, payment_frequency
        FROM purchase_orders
        WHERE payment_type = 'periodic'
    """, engine)
    df_periodic.to_csv(os.path.join(output_dir, "periodic.csv"), index=False)

    logger.info("CSV exports complete.")