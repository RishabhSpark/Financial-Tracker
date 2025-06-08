from db.database import SessionLocal, PurchaseOrder, Milestone, PaymentSchedule

def insert_or_replace_po(po_dict: dict):
    session = SessionLocal()
    po_id = po_dict.get("po_id")

    # delete if PO exists (also cascades delete milestones and schedules)
    existing_po = session.query(PurchaseOrder).filter_by(po_id=po_id).first()
    if existing_po:
        session.delete(existing_po)
        session.commit()

    # insert main PO
    po = PurchaseOrder(
        po_id=po_dict["po_id"],
        client_name=po_dict.get("client_name"),
        amount=po_dict.get("amount"),
        status=po_dict.get("status"),
        payment_terms=po_dict.get("payment_terms"),
        payment_type=po_dict.get("payment_type"),
        start_date=po_dict.get("start_date"),
        end_date=po_dict.get("end_date"),
        duration_months=po_dict.get("duration_months"),
        payment_frequency=po_dict.get("payment_frequency")
    )

    session.add(po)

    # insert based on type
    if po.payment_type == "milestone":
        for ms in po_dict.get("milestones", []):
            session.add(Milestone(po_id=po_id, **ms))

    elif po.payment_type == "distributed":
        for sched in po_dict.get("payment_schedule", []):
            session.add(PaymentSchedule(po_id=po_id, **sched))

    session.commit()
    session.close()


def get_po_with_schedule(po_id: str):
    session = SessionLocal()
    try:
        po = session.query(PurchaseOrder).filter_by(po_id=po_id).first()
        if not po:
            return None

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
            "payment_frequency": po.payment_frequency
        }

        # Add payment schedule list if any
        po_dict["payment_schedule"] = []
        for payment in po.payment_schedule:
            po_dict["payment_schedule"].append({
                "payment_date": payment.payment_date,
                "payment_amount": payment.payment_amount,
                "payment_description": payment.payment_description
            })

        # Similarly, you can add milestones here if needed

        return po_dict
    finally:
        session.close()
