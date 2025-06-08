import os
import json
import pandas as pd
from sqlalchemy import create_engine
from db.database import PurchaseOrder, SessionLocal

def export_all_pos_json(output_path="output/purchase_orders.json"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    session = SessionLocal()

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

        if po.payment_type == "milestone":
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
            po_dict["payment_schedule"] = [
                {
                    "payment_date": sched.payment_date,
                    "payment_amount": sched.payment_amount,
                    "payment_description": sched.payment_description,
                }
                for sched in po.payment_schedule
            ]

        elif po.payment_type == "periodic":
            po_dict["payment_schedule"] = {"payment_frequency": po.payment_frequency}
            po_dict["duration_months"] = po.duration_months

        export_data.append(po_dict)

    session.close()

    with open(output_path, "w") as f:
        json.dump(export_data, f, indent=2)

    print(f"Exported {len(export_data)} purchase orders with nested data to {output_path}")


def export_all_csvs(output_dir="output/"):
    os.makedirs(output_dir, exist_ok=True)
    engine = create_engine("sqlite:///po_database.db")

    # 1. Export purchase_orders.csv
    df_po = pd.read_sql("SELECT id, po_id, client_name, amount, status, payment_terms, payment_type, start_date, end_date, duration_months FROM purchase_orders", engine)
    df_po.to_csv(os.path.join(output_dir, "purchase_orders.csv"), index=False)

    # 2. Export milestones.csv
    df_ms = pd.read_sql("SELECT id, po_id, milestone_name, milestone_description, milestone_due_date, milestone_percentage FROM milestones", engine)
    df_ms.to_csv(os.path.join(output_dir, "milestones.csv"), index=False)

    # 3. Export distributed.csv (previously payment_schedule)
    df_sched = pd.read_sql("SELECT id, po_id, payment_date, payment_amount, payment_description FROM payment_schedule", engine)
    df_sched.to_csv(os.path.join(output_dir, "distributed.csv"), index=False)

    # 4. Export periodic.csv from purchase_orders where type is 'periodic'
    df_periodic = pd.read_sql("""
        SELECT id, po_id, start_date, end_date, payment_frequency
        FROM purchase_orders
        WHERE payment_type = 'periodic'
    """, engine)
    df_periodic.to_csv(os.path.join(output_dir, "periodic.csv"), index=False)

    print("CSV exports complete.")