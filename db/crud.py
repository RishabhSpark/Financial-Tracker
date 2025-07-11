from db.database import SessionLocal, PurchaseOrder, Milestone, PaymentSchedule, DriveFile
from datetime import datetime

def insert_or_replace_po(po_dict: dict):
    session = SessionLocal()
    po_id = po_dict.get("po_id")

    existing_po = session.query(PurchaseOrder).filter_by(po_id=po_id).first()
    if existing_po:
        # Update all fields
        existing_po.client_name = po_dict.get("client_name")
        existing_po.amount = po_dict.get("amount")
        existing_po.status = po_dict.get("status")
        existing_po.payment_terms = po_dict.get("payment_terms")
        existing_po.payment_type = po_dict.get("payment_type")
        existing_po.start_date = po_dict.get("start_date")
        existing_po.end_date = po_dict.get("end_date")
        existing_po.duration_months = po_dict.get("duration_months")
        existing_po.payment_frequency = po_dict.get("payment_frequency")
        existing_po.project_owner = po_dict.get("project_owner")
        # Remove old milestones and payment schedules
        session.query(Milestone).filter_by(po_id=po_id).delete()
        session.query(PaymentSchedule).filter_by(po_id=po_id).delete()
        # Add new milestones or payment schedules
        if existing_po.payment_type == "milestone":
            for ms in po_dict.get("milestones", []):
                session.add(Milestone(po_id=po_id, **ms))
        elif existing_po.payment_type == "distributed":
            for sched in po_dict.get("payment_schedule", []):
                session.add(PaymentSchedule(po_id=po_id, **sched))
        session.commit()
        session.close()
        return

    # PO does not exist, proceed with insertion
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
        payment_frequency=po_dict.get("payment_frequency"),
        project_owner=po_dict.get("project_owner")
    )
    session.add(po)
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
            "payment_frequency": po.payment_frequency,
            "project_owner": po.project_owner
        }

        # Add payment schedule list if any
        po_dict["payment_schedule"] = []
        for payment in po.payment_schedule:
            po_dict["payment_schedule"].append({
                "payment_date": payment.payment_date,
                "payment_amount": payment.payment_amount,
                "payment_description": payment.payment_description
            })

        po_dict["milestones"] = []
        for ms in po.milestones:
            po_dict["milestones"].append({
                "milestone_name": ms.milestone_name,
                "milestone_description": ms.milestone_description,
                "milestone_due_date": ms.milestone_due_date,
                "milestone_percentage": ms.milestone_percentage
            })            
        return po_dict
    finally:
        session.close()


def upsert_drive_files_sqlalchemy(files_data: list[dict]):
    """
    Upserts (updates or inserts) DriveFile records using SQLAlchemy.
    Deletes records from the DB that are not in the provided files_data list based on ID.

    Args:
        files_data: A list of dictionaries, where each dictionary
                    represents a file and contains 'id', 'name',
                    and 'modifiedTime' (as an ISO 8601 string).
    """
    session = SessionLocal()
    try:
        print(f"[DEBUG] upsert_drive_files_sqlalchemy called with {len(files_data)} files.")
        # Get all current DB file IDs for efficient deletion check later
        current_db_file_ids = {db_file.id for db_file in session.query(DriveFile.id).all()}
        print(f"[DEBUG] Current DB file IDs: {current_db_file_ids}")
        processed_ids = set()

        for file_data in files_data:
            file_id = file_data.get('id')
            file_name = file_data.get('name')
            print(f"[DEBUG] Processing file: id={file_id}, name={file_name}")
            processed_ids.add(file_id)

            # Robustly handle missing or malformed modifiedTime
            modified_time_str = file_data.get('modifiedTime')
            last_edited_dt = None
            if modified_time_str:
                try:
                    if modified_time_str.endswith('Z'):
                        last_edited_dt = datetime.fromisoformat(modified_time_str[:-1] + '+00:00')
                    else:
                        last_edited_dt = datetime.fromisoformat(modified_time_str)
                except Exception as ve:
                    print(f"[ERROR] Could not parse modifiedTime for file {file_id}: {modified_time_str}. Error: {ve}")
                    last_edited_dt = datetime.utcnow()  # Fallback to now
            else:
                print(f"[WARN] No modifiedTime for file {file_id}, using current UTC time.")
                last_edited_dt = datetime.utcnow()

            existing_file = session.query(DriveFile).filter_by(id=file_id).first()

            if existing_file:
                if existing_file.name != file_name or existing_file.last_edited != last_edited_dt:
                    print(f"[DEBUG] Updating file {file_id}")
                    existing_file.name = file_name
                    existing_file.last_edited = last_edited_dt
                else:
                    print(f"[DEBUG] No update needed for file {file_id}")
            else:
                print(f"[DEBUG] Inserting new file {file_id}")
                new_file = DriveFile(
                    id=file_id,
                    name=file_name,
                    last_edited=last_edited_dt
                )
                session.add(new_file)

        ids_to_delete = current_db_file_ids - processed_ids
        if ids_to_delete:
            print(f"[DEBUG] Deleting files from DB: {ids_to_delete}")
            session.query(DriveFile).filter(DriveFile.id.in_(ids_to_delete)).delete(synchronize_session=False)
        else:
            print("[DEBUG] No files to delete from DB.")
        session.commit()
        print("[DEBUG] upsert_drive_files_sqlalchemy committed successfully.")
    except Exception as e:
        session.rollback()
        print(f"[ERROR] Exception in upsert_drive_files_sqlalchemy: {e}")
        raise
    finally:
        session.close()
        print("[DEBUG] upsert_drive_files_sqlalchemy session closed.")


def get_all_drive_files():
    """
    Returns a dict mapping file name to (last_edited, id) for all files in the drive_files table.
    """
    session = SessionLocal()
    try:
        files = session.query(DriveFile).all()
        # Map: name -> (last_edited, id)
        return {f.name: (f.last_edited, f.id) for f in files}
    finally:
        session.close()


def delete_po_by_drive_file_id(file_id):
    """
    Deletes all PO-related data (purchase order, milestones, payment schedule) for a given drive file id.
    Assumes PO id is the same as drive file id or can be mapped (adjust as needed).
    """
    session = SessionLocal()
    try:
        # Find all POs linked to this drive file id (assuming po_id == file_id)
        po = session.query(PurchaseOrder).filter_by(po_id=file_id).first()
        if po:
            # Delete related milestones and payment schedules (cascade should handle if set)
            session.delete(po)
            session.commit()
    finally:
        session.close()
