import os
import io
import tempfile
import numpy as np
import pandas as pd
import subprocess
from PyPDF2 import PdfReader
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseDownload
from extractor.run_extraction import run_pipeline
from functools import wraps
from db.crud import insert_or_replace_po, upsert_drive_files_sqlalchemy, get_all_drive_files, delete_po_by_drive_file_id, get_po_with_schedule
from db.database import init_db, PurchaseOrder, SessionLocal, PaymentSchedule, Milestone
from flask import Flask, request, redirect, session, url_for, render_template,  send_file, render_template_string, jsonify, flash, g
from extractor.pdf_processing.extract_blocks import extract_blocks
from extractor.pdf_processing.extract_tables import extract_tables
from extractor.pdf_processing.format_po import format_po_for_llm
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

from app.core.logger import setup_logger

logger = setup_logger()

load_dotenv()
logger.info("Loaded environment variables from .env file.")

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'supersecret123')
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
CLIENT_SECRETS_FILE = 'client_secret.json'


USERS = {}
for i in range(1, 10):
    username = os.getenv(f'USER_{i}_NAME')
    password = os.getenv(f'USER_{i}_PASSWORD')
    if username and password:
        USERS[username] = password
        logger.debug(f"Loaded user: {username}")

def build_credentials(creds_dict):
    return Credentials(**creds_dict)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            logger.info("Unauthorized access attempt to %s", request.path)
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('login'))
        logger.debug("User %s accessed %s", session.get('username', 'Unknown'), request.path)
        return f(*args, **kwargs)
    return decorated_function


@app.before_request
def load_logged_in_user():
    g.user = None
    if 'username' in session:
        g.user = session['username']
    logger.info("User %s is accessing %s", g.user, request.path)

@app.route('/add_client', methods=['GET', 'POST'])
def add_unconfirmed_order():
    if request.method == 'POST':
        form = request.form
        logger.info("Received POST request to /add_client from user '%s' with data: %s", g.user, dict(form))
        
        # Normalize status to one of the allowed values
        raw_status = form.get("status", "unconfirmed").strip().lower()
        if raw_status == "confirmed":
            status = "Confirmed"
        elif raw_status == "unconfirmed":
            status = "Unconfirmed"
        else:
            status = "unspecified"
            logger.warning("Unknown status value received: '%s' (user: %s)", raw_status, g.user)
        
        po_dict = {
            "po_id": generate_unconfirmed_po_id(),
            "client_name": form.get("client_name"),
            "amount": form.get("amount"),
            "status": status,
            "payment_terms": form.get("payment_terms"),
            "payment_type": form.get("payment_type"),
            "start_date": form.get("start_date"),
            "end_date": form.get("end_date"),
            "duration_months": form.get("duration_months"),
            "project_owner": form.get("project_owner"),
            "payment_frequency": form.get("payment_frequency"),
        }
        logger.debug("Constructed PO dict: %s", po_dict)
        
        # Handle distributed payments
        if form.get("payment_type") == "distributed":
            payment_schedule = []
            for key in form.keys():
                if key.startswith("payment_date_"):
                    index = key.split("_")[-1]
                    date = form.get(f"payment_date_{index}")
                    amount = form.get(f"payment_amount_{index}")
                    if date and amount:
                        payment_schedule.append({"payment_date": date, "payment_amount": amount})
            po_dict["payment_schedule"] = payment_schedule
            logger.info("Processed distributed payment schedule for PO %s: %s", po_dict["po_id"], payment_schedule)
        # Handle milestones
        if form.get("payment_type") == "milestone":
            milestones = []
            total_percentage = 0.0
            for key in form:
                if key.startswith("milestone_name_"):
                    index = key.split("_")[-1]
                    try:
                        percent = float(form.get(f"milestone_percent_{index}", 0))
                    except ValueError:
                        percent = 0
                        logger.warning("Invalid milestone percent for index %s (user: %s)", index, g.user)
                    total_percentage += percent
                    milestones.append({
                        "milestone_name": f"Milestone {index}",
                        "milestone_description": form.get(f"milestone_description_{index}"),
                        "milestone_due_date": form.get(f"milestone_due_{index}"),
                        "milestone_percentage": form.get(f"milestone_percent_{index}"),
                    })
            if round(total_percentage, 2) != 100.00:
                logger.error("Milestone percentages do not add up to 100%% (got %.2f) for PO %s by user %s", total_percentage, po_dict["po_id"], g.user)
                flash("Milestone percentages must add up to 100%.", "danger")
                return render_template("add_unconfirmed_order.html", form_data=request.form)
            po_dict["milestones"] = milestones
            logger.info("Processed milestones for PO %s: %s", po_dict["po_id"], milestones)
        # Insert into DB
        try:
            insert_or_replace_po(po_dict)
            logger.info("Inserted/updated PO in database: %s (user: %s)", po_dict["po_id"], g.user)
        except Exception as e:
            logger.error("Error inserting PO into database for user %s: %s", g.user, e, exc_info=True)
            flash("Error saving purchase order.", "danger")
            return render_template("add_unconfirmed_order.html", form_data=request.form)
        # Update output files
        try:
            from extractor.export import export_all_pos_json, export_all_csvs
            from forecast_processor import run_forecast_processing
            export_all_pos_json()
            export_all_csvs()
            run_forecast_processing(input_json_path="./output/purchase_orders.json")
            logger.info("Exported all POs and ran forecast processing after PO insert (PO: %s, user: %s)", po_dict["po_id"], g.user)
        except Exception as e:
            logger.error("Error exporting or running forecast processing for PO %s by user %s: %s", po_dict["po_id"], g.user, e, exc_info=True)
        return redirect(url_for("forecast"))
    return render_template("add_unconfirmed_order.html", form_data={})


@app.route('/')
def index():
    logger.info("Rendering login page (index route) for user: %s", g.user if hasattr(g, 'user') else None)
    return render_template('login.html')


@app.route('/login', methods=['GET', 'POST'])
def login():

    if "logged_in" in session and session['logged_in']:
        logger.info("User '%s' already logged in, rendering index page.", session.get('username'))
        return render_template('index.html')
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        logger.info("Login attempt for username: '%s'", username)
        if username in USERS and check_password_hash(USERS[username], password):
            session['logged_in'] = True
            session['username'] = username
            logger.info("User '%s' logged in successfully.", username)
            flash(f'Logged in successfully as {username}!', 'success')
            return render_template('index.html')
        else:
            logger.warning("Failed login attempt for username: '%s'", username)
            flash('Invalid username or password.', 'danger')
            return render_template('login.html')
    logger.info("Rendering login page (GET request)")
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logger.info("User '%s' logging out.", session.get('username'))
    session.pop('logged_in', None)
    session.pop('username', None)
    session.pop('credentials', None)
    flash('You have been logged out.', 'info')
    session.clear()
    return redirect(url_for('login'))


@app.route('/authorize')
@login_required
def authorize():
    logger.info("User '%s' initiating Google OAuth authorization.", session.get('username'))
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for('oauth2callback', _external=True)
    )
    auth_url, _ = flow.authorization_url(prompt='consent')
    return redirect(auth_url)


@app.route('/oauth2callback')
@login_required
def oauth2callback():
    logger.info("User '%s' returned from Google OAuth callback.", session.get('username'))
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for('oauth2callback', _external=True)
    )
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    session['credentials'] = creds_to_dict(creds)
    logger.info("User '%s' successfully authenticated with Google OAuth.", session.get('username'))
    return redirect(url_for('drive_folder_upload'))


@app.route('/process_pdf/<file_id>')
@login_required
def process_pdf(file_id):

    creds = Credentials.from_authorized_user_info(session['credentials'])
    service = build('drive', 'v3', credentials=creds)

    try:
        file = service.files().get(fileId=file_id, fields='name, mimeType').execute()
        if file['mimeType'] != 'application/pdf':
            return "<p>Only PDF files are supported for processing.</p>"

        request_drive = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request_drive)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        fh.seek(0)

        temp_dir = tempfile.gettempdir()
        temp_pdf_path = os.path.join(temp_dir, f"temp_pdf_{file_id}.pdf")

        with open(temp_pdf_path, 'wb') as f:
            f.write(fh.getvalue())

        try:
            text_blocks = extract_blocks(temp_pdf_path)
            tables = extract_tables(temp_pdf_path)

            llm_formatted_content = format_po_for_llm(text_blocks, tables)

            return f"""
            <h1>Processed PDF: {file['name']}</h1>
            <h2>LLM Formatted Content (for direct use):</h2>
            <pre>{llm_formatted_content}</pre>
            """

        finally:
            if os.path.exists(temp_pdf_path):
                os.remove(temp_pdf_path)

    except Exception as e:
        return f"<p>An error occurred: {e}</p>"


# @app.route('/download/<file_id>')
# @login_required
# def download_pdf(file_id):

#     creds = Credentials.from_authorized_user_info(session['credentials'])
#     service = build('drive', 'v3', credentials=creds)

#     file = service.files().get(fileId=file_id, fields='name, mimeType').execute()
#     file_name = file['name']
#     mime_type = file['mimeType']

#     if mime_type != 'application/pdf' and not file_name.endswith('.pdf'):
#         return "<p>Only PDF files are supported for download.</p>"

#     project_root = os.path.dirname(os.path.abspath(__file__))
#     save_dir = os.path.join(project_root, 'input', 'POs')
#     os.makedirs(save_dir, exist_ok=True)
#     save_path = os.path.join(save_dir, file_name)

#     request = service.files().get_media(fileId=file_id)
#     with open(save_path, "wb") as f:
#         downloader = MediaIoBaseDownload(f, request)
#         done = False
#         while not done:
#             status, done = downloader.next_chunk()

#     print(f"✅ PDF saved to: {save_path}")
#     return f"<p>✅ PDF downloaded and saved to <code>{save_path}</code></p>"


@app.route("/forecast", methods=["GET"])
@login_required
def forecast():
    logger.info("User '%s' accessed forecast page.", session.get('username'))
    creds = Credentials.from_authorized_user_info(session['credentials'])
    def parse_checklist(param):
        val = request.args.get(param, default=None, type=str)
        if val is None or val == '':
            return []
        return [v.strip() for v in val.split(",") if v.strip()]

    client_names_selected = parse_checklist('client_name')
    po_nos_selected = parse_checklist('po_no')
    project_owners_selected = parse_checklist('project_owner')
    statuses_selected = parse_checklist('status')
    start_month_selected = request.args.get('start_month', default=None, type=str)
    end_month_selected = request.args.get('end_month', default=None, type=str)

    df = None
    try:
        df = pd.read_csv("forecast_output.csv")
        if 'Inflow (USD)' in df.columns:
            df['Inflow (USD)'] = pd.to_numeric(
                df['Inflow (USD)'], errors='coerce').fillna(0.0)
        logger.info("Loaded forecast_output.csv for forecast page.")
    except Exception as e:
        logger.error("Error loading forecast_output.csv: %s", e, exc_info=True)
        df = pd.DataFrame()

    # Prepare dropdown options
    client_names = sorted(df['Client Name'].dropna(
    ).unique()) if 'Client Name' in df.columns else []
    po_nos = sorted([str(po) for po in df['PO No'].dropna().unique()]
                    ) if 'PO No' in df.columns else []
    months = sorted(df['Month'].dropna().unique()
                    ) if 'Month' in df.columns else []
    project_owners = sorted(df['Project Owner'].dropna().unique()) if 'Project Owner' in df.columns else []
    statuses = sorted(df['Status'].dropna().unique()) if 'Status' in df.columns else []

    # Apply filters (multi-select for client/po/owner/status, range for months)
    filtered_df = df.copy()
    if client_names_selected:
        filtered_df = filtered_df[filtered_df['Client Name'].isin(
            client_names_selected)]
    if po_nos_selected:
        filtered_df = filtered_df[filtered_df['PO No'].astype(
            str).isin(po_nos_selected)]
    if project_owners_selected:
        filtered_df = filtered_df[filtered_df['Project Owner'].isin(project_owners_selected)]
    if statuses_selected:
        filtered_df = filtered_df[filtered_df['Status'].isin(statuses_selected)]
    if start_month_selected:
        filtered_df = filtered_df[filtered_df['Month'] >= start_month_selected]
    if end_month_selected:
        filtered_df = filtered_df[filtered_df['Month'] <= end_month_selected]

    logger.debug("Filters applied on forecast: clients=%s, pos=%s, owners=%s, statuses=%s, start_month=%s, end_month=%s",
        client_names_selected, po_nos_selected, project_owners_selected, statuses_selected, start_month_selected, end_month_selected)

    # Generate filtered pivot table
    pivot_html = generate_pivot_table_html(filtered_df)

    logger.info("Rendering forecast page for user '%s'.", session.get('username'))
    return render_template(
        "forecast.html",
        pivot_table=pivot_html,
        client_names=client_names,
        po_nos=po_nos,
        months=months,
        project_owners=project_owners,
        statuses=statuses,
        selected_client=client_names_selected,
        selected_po=po_nos_selected,
        selected_owner=project_owners_selected,
        selected_status=statuses_selected,
        selected_start_month=[
            start_month_selected] if start_month_selected else [],
        selected_end_month=[end_month_selected] if end_month_selected else []
    )


def generate_pivot_table_html(df=None):
    from app.core.logger import setup_logger
    logger = setup_logger()
    try:
        logger.info("Generating pivot table HTML.")
        if df is None:
            logger.debug("No DataFrame provided, loading 'forecast_output.csv'.")
            df = pd.read_csv("forecast_output.csv")

        # Ensure 'Inflow (USD)' is numeric and NaNs are 0.0.
        if 'Inflow (USD)' in df.columns:
            logger.debug("Converting 'Inflow (USD)' to numeric and filling NaNs with 0.0.")
            df['Inflow (USD)'] = pd.to_numeric(
                df['Inflow (USD)'], errors='coerce').fillna(0.0)
        else:
            logger.warning("'Inflow (USD)' column missing, creating empty float64 column.")
            df['Inflow (USD)'] = pd.Series(dtype='float64')

        all_months_for_pivot = []
        if 'Month' in df.columns and not df['Month'].dropna().empty:
            logger.debug("Parsing 'Month' column to datetime for range calculation.")
            month_as_datetime = pd.to_datetime(
                df['Month'], format='%Y-%m', errors='coerce')
            month_as_datetime.dropna(inplace=True)
            if not month_as_datetime.empty:
                min_month = month_as_datetime.min()
                max_month = month_as_datetime.max()
                all_months_for_pivot = pd.date_range(
                    min_month, max_month, freq='MS').strftime('%Y-%m').tolist()
                logger.info("Pivot will include months: %s", all_months_for_pivot)
            else:
                logger.warning("No valid months found in 'Month' column.")
        else:
            logger.warning("'Month' column missing or empty.")

        for col in ["Client Name", "PO No", "Project Owner", "Status", "Month"]:
            if col not in df.columns:
                logger.warning("Column '%s' missing, creating empty object column.", col)
                df[col] = pd.Series(dtype='object')

        # --- Pivot Table with Totals ---
        logger.debug("Creating pivot table.")
        pivot = df.pivot_table(
            index=["Client Name", "PO No", "Project Owner", "Status"],
            columns="Month",
            values="Inflow (USD)",
            aggfunc="sum",
            fill_value=0.0
        )
        pivot = pivot.reindex(columns=all_months_for_pivot, fill_value=0.0)
        pivot.reset_index(inplace=True)

        # Format month columns to 'Month YYYY' (e.g., 'May 2025')
        month_col_map = {}
        for m in all_months_for_pivot:
            try:
                dt = pd.to_datetime(m, format="%Y-%m")
                month_col_map[m] = dt.strftime("%b %Y")
            except Exception:
                logger.warning("Could not format month column: %s", m)
                month_col_map[m] = m
        pivot.rename(columns=month_col_map, inplace=True)
        formatted_month_cols = [month_col_map.get(
            m, m) for m in all_months_for_pivot]

        # Add row-wise total (sum across months for each PO)
        month_cols = formatted_month_cols
        if month_cols:
            logger.debug("Adding row-wise totals across months.")
            pivot['Total'] = pivot[month_cols].sum(axis=1)
            pivot['Total'] = np.round(pivot['Total'])
        else:
            logger.warning("No month columns for row-wise totals.")
            pivot['Total'] = 0.0

        # Add a serial number column
        if not pivot.empty:
            logger.debug("Adding serial number column.")
            pivot.insert(0, 'S.No', range(1, 1 + len(pivot)))
        else:
            logger.warning("Pivot table is empty, creating empty columns for display.")
            if 'S.No' not in pivot.columns:
                pivot['S.No'] = pd.Series(dtype='int')
            if "Client Name" not in pivot.columns:
                pivot["Client Name"] = pd.Series(dtype='object')
            if "PO No" not in pivot.columns:
                pivot["PO No"] = pd.Series(dtype='object')
            if "Status" not in pivot.columns:
                pivot["Status"] = pd.Series(dtype='object')

        # Add a total row at the bottom (sum for each month and for the 'Total' column)
        if not pivot.empty and month_cols:
            logger.debug("Adding total row at the bottom of the pivot table.")
            total_row = [''] * len(pivot.columns)
            # Find column indices
            s_no_idx = pivot.columns.get_loc(
                'S.No') if 'S.No' in pivot.columns else None
            client_idx = pivot.columns.get_loc(
                'Client Name') if 'Client Name' in pivot.columns else None
            po_idx = pivot.columns.get_loc(
                'PO No') if 'PO No' in pivot.columns else None
            # Label the total row
            if client_idx is not None:
                total_row[client_idx] = 'TOTAL'
            if po_idx is not None:
                total_row[po_idx] = ''
            # Fill month totals
            for m in month_cols:
                col_idx = pivot.columns.get_loc(m)
                total_row[col_idx] = pivot[m].sum()
            # Fill grand total
            total_col_idx = pivot.columns.get_loc('Total')
            total_row[total_col_idx] = pivot['Total'].sum()
            # Insert the total row as a DataFrame
            total_df = pd.DataFrame([total_row], columns=pivot.columns)
            # Concatenate to the pivot
            pivot = pd.concat([pivot, total_df], ignore_index=True)
            logger.info("Total row added to pivot table.")

        # Convert the pivot table to HTML, formatting float values to two decimal places
        def format_float(val):
            try:
                return f"{float(val):.2f}"
            except:
                return val

        def format_usd(val):
            try:
                return "$" + format(int(round(float(val))), ",")
            except:
                return val
        html = pivot.to_html(
            classes="table table-striped table-bordered",
            border=0,
            index=False,
            formatters={col: format_usd for col in pivot.columns if col not in [
                'S.No', 'Client Name', 'PO No', 'Project Owner', 'Status']},
            na_rep=""
        )
        logger.info("Pivot table HTML generated successfully.")
        return html
    except FileNotFoundError:
        logger.error("forecast_output.csv not found. Please generate the forecast first.")
        return "<p>Error: <code>forecast_output.csv</code> not found. Please generate the forecast first.</p>"
    except Exception as e:
        logger.error("Error generating pivot table: %s", e, exc_info=True)
        return f"<p>Error generating pivot table: {e}</p>"


@app.route("/download-forecast")
@login_required
def download_forecast():
    return send_file("forecast_pivot.xlsx", as_attachment=True)


def creds_to_dict(creds):
    return {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }


def get_drive_tree(service, parent_id='root'):
    """
    Recursively builds a tree of files/folders from Google Drive.
    Returns a nested dict structure.
    """
    logger.info("Building Google Drive tree for parent_id='%s'", parent_id)
    query = f"'{parent_id}' in parents and trashed = false"
    try:
        results = service.files().list(
            q=query, fields="files(id, name, mimeType)", pageSize=1000).execute()
        items = results.get('files', [])
        logger.debug("Found %d items in folder '%s'", len(items), parent_id)
    except Exception as e:
        logger.error("Error listing files for parent_id='%s': %s", parent_id, e, exc_info=True)
        return []
    tree = []
    for item in items:
        node = {
            'id': item['id'],
            'name': item['name'],
            'mimeType': item['mimeType']
        }
        if item['mimeType'] == 'application/vnd.google-apps.folder':
            logger.debug("Recursing into subfolder '%s' (id=%s)", item['name'], item['id'])
            node['children'] = get_drive_tree(service, item['id'])
        tree.append(node)
    logger.info("Completed building tree for parent_id='%s' (items: %d)", parent_id, len(tree))
    return tree


@app.route('/drive_tree_children/<folder_id>')
@login_required
def drive_tree_children(folder_id):
    logger.info("Fetching children for Drive folder_id='%s' (user: %s)", folder_id, session.get('username'))
    if 'credentials' not in session:
        logger.warning("No credentials in session for user: %s", session.get('username'))
        return ''
    creds = Credentials.from_authorized_user_info(session['credentials'])
    service = build('drive', 'v3', credentials=creds)
    children = get_drive_tree(service, folder_id)

    def render_tree(nodes, parent_path=""):
        html = '<ul style="margin-left:20px">'
        for node in nodes:
            if node['mimeType'] == 'application/vnd.google-apps.folder':
                folder_path = f"{parent_path}/{node['name']}" if parent_path else node['name']
                html += f'<li class="folder"><span class="toggle">+</span> <span class="folder-name">📁 {node["name"]}</span> <button class="select-folder-btn" data-folder-path="{folder_path}">Select Folder</button><div class="children" style="display:none" data-folder-id="{node["id"]}" data-folder-path="{folder_path}"></div></li>'
            else:
                html += f'<li class="file">📄 {node["name"]}</li>'
        html += '</ul>'
        return html
    parent_path = request.args.get('parent_path', '')
    logger.debug("Rendering tree HTML for folder_id='%s' (user: %s)", folder_id, session.get('username'))
    return render_tree(children, parent_path)


@app.route('/drive_tree')
@login_required
def drive_tree():
    logger.info("Rendering drive tree for user: %s", session.get('username'))
    if 'credentials' not in session:
        logger.warning("No credentials in session for user: %s", session.get('username'))
        return redirect(url_for('authorize'))

    creds = Credentials.from_authorized_user_info(session['credentials'])
    service = build('drive', 'v3', credentials=creds)
    tree = get_drive_tree(service)

    def render_tree(nodes, parent_path=""):
        html = '<ul>'
        for node in nodes:
            if node['mimeType'] == 'application/vnd.google-apps.folder':
                folder_path = f"{parent_path}/{node['name']}" if parent_path else node['name']
                html += f'''
                    <li class="folder">
                        <span class="toggle">+</span>
                        <span class="folder-name">📁 {node["name"]}</span>
                        <button class="select-folder-btn" data-folder-path="{folder_path}">Select Folder</button>
                        <div class="children" style="display:none" data-folder-id="{node["id"]}" data-folder-path="{folder_path}"></div>
                    </li>
                '''
            else:
                html += f'<li class="file">📄 {node["name"]}</li>'
        html += '</ul>'
        return html

    tree_html = render_tree(tree)
    logger.info("Drive tree HTML rendered for user: %s", session.get('username'))
    return render_template("drive_tree.html", tree_html=tree_html)


def list_all_files_in_folder(service, folder_id):
    """
    Recursively list all files in a Google Drive folder by folder_id.
    Returns a list of dicts: [{id, name, modifiedTime}]
    """
    logger.info("Listing all files in Google Drive folder_id='%s'", folder_id)
    files = []
    page_token = None
    try:
        while True:
            response = service.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
                pageToken=page_token
            ).execute()
            logger.debug("Found %d items in folder '%s' (page_token=%s)", len(response.get('files', [])), folder_id, page_token)
            for file in response.get('files', []):
                if file['mimeType'] == 'application/vnd.google-apps.folder':
                    logger.debug("Recursing into subfolder '%s' (id=%s)", file['name'], file['id'])
                    files.extend(list_all_files_in_folder(service, file['id']))
                else:
                    files.append({
                        'id': file['id'],
                        'name': file['name'],
                        'mimeType': file['mimeType'],
                        'modifiedTime': file.get('modifiedTime', '')
                    })
            page_token = response.get('nextPageToken', None)
            if not page_token:
                break
        logger.info("Completed listing files for folder_id='%s' (total files: %d)", folder_id, len(files))
    except Exception as e:
        logger.error("Error listing files in folder_id='%s': %s", folder_id, e, exc_info=True)
    return files


def render_files_table(files):
    if not files:
        logger.info("No files found to render in files table.")
        return '<p>No files found in this folder.</p>'
    logger.info("Rendering files table for %d files.", len(files))
    html = '<table border="1" id="drive-files-table"><tr><th>Filename</th><th>Last Edited</th></tr>'
    for f in files:
        html += f'<tr><td>{f["name"]}</td><td>{f["modifiedTime"]}</td></tr>'
    html += '</table>'
    return html


@app.route('/confirm_folder', methods=['POST'])
@login_required
def confirm_folder():
    logger.info("Confirming folder for Drive sync (user: %s)", session.get('username'))
    if 'credentials' not in session:
        logger.warning("No credentials in session for user: %s", session.get('username'))
        return '<p>Not authorized.</p>', 401
    creds = Credentials.from_authorized_user_info(session['credentials'])
    service = build('drive', 'v3', credentials=creds)
    data = request.get_json()
    folder_id = data.get('folder_id')
    if not folder_id:
        logger.warning("No folder_id provided in confirm_folder request (user: %s)", session.get('username'))
        return '<p>No folder selected.</p>', 400
    files = list_all_files_in_folder(service, folder_id)
    try:
        upsert_drive_files_sqlalchemy(files)  # Use the new SQLAlchemy function
        logger.info("Upserted %d drive files into database for folder_id='%s' (user: %s)", len(files), folder_id, session.get('username'))
    except Exception as e:
        logger.error("Error upserting drive files for folder_id='%s' (user: %s): %s", folder_id, session.get('username'), e, exc_info=True)
        return f"<p>Error updating database: {e}</p>", 500
    return render_files_table(files)


@app.route('/extract_text_from_drive_folder')
@login_required
def extract_text_from_drive_folder():
    logger.info("Extract text from drive folder route called by user: %s", session.get('username'))
    if 'credentials' not in session:
        logger.warning("No credentials in session for user: %s", session.get('username'))
        return redirect(url_for('authorize'))

    folder_id = request.args.get('folder_id')
    if not folder_id:
        logger.warning("No folder_id provided in request by user: %s", session.get('username'))
        return "Please provide a 'folder_id' query parameter.", 400

    creds = Credentials.from_authorized_user_info(session['credentials'])
    service = build('drive', 'v3', credentials=creds)

    try:
        logger.info("Fetching metadata for folder_id='%s'", folder_id)
        folder_metadata = service.files().get(
            fileId=folder_id, fields="id, name, mimeType").execute()
        if folder_metadata.get('mimeType') != 'application/vnd.google-apps.folder':
            logger.error("Provided ID '%s' is not a folder (user: %s)", folder_id, session.get('username'))
            return f"The provided ID '{folder_id}' is not a folder.", 400
        logger.info("Accessing folder: %s (ID: %s)", folder_metadata.get('name'), folder_id)
    except Exception as e:
        logger.error("Invalid folder_id or error accessing folder: %s (user: %s)", e, session.get('username'), exc_info=True)
        return f"Invalid folder_id or error accessing folder: {e}", 400

    all_files_in_folder = list_all_files_in_folder(service, folder_id)
    pdf_files_found = False
    extracted_texts_summary = []

    logger.info("Starting PDF text extraction for folder ID: %s", folder_id)
    db_files = get_all_drive_files()  # {name: (last_edited, id)}
    current_drive_file_names = set()
    current_drive_file_ids = set()
    for file_item in all_files_in_folder:
        if file_item.get('mimeType') == 'application/pdf':
            current_drive_file_names.add(file_item['name'])
            current_drive_file_ids.add(file_item['id'])
    db_file_names = set(db_files.keys())
    for db_name, (db_last_edited, db_id) in db_files.items():
        if db_name not in current_drive_file_names:
            logger.info("File '%s' (id=%s) deleted from Drive. Removing from database...", db_name, db_id)
            delete_po_by_drive_file_id(db_id)
    for file_item in all_files_in_folder:
        if file_item.get('mimeType') != 'application/pdf':
            continue
        file_name = file_item['name']
        file_id = file_item['id']
        file_last_edited = file_item.get('modifiedTime')
        from datetime import datetime
        file_last_edited_dt = None
        if file_last_edited:
            try:
                if file_last_edited.endswith('Z'):
                    file_last_edited_dt = datetime.fromisoformat(
                        file_last_edited[:-1] + '+00:00')
                else:
                    file_last_edited_dt = datetime.fromisoformat(
                        file_last_edited)
            except Exception:
                logger.warning("Could not parse modifiedTime for file '%s' (id=%s)", file_name, file_id)
        db_entry = db_files.get(file_name)
        if db_entry:
            db_last_edited, db_id = db_entry
            if db_last_edited == file_last_edited_dt:
                logger.info("Skipping %s (unchanged)", file_name)
                continue  # Skip unchanged
            else:
                logger.info("Updating %s (timestamp changed)", file_name)
                delete_po_by_drive_file_id(file_id)
        else:
            logger.info("Adding new file %s", file_name)
        try:
            logger.info("Downloading file '%s' (id=%s)", file_name, file_id)
            request_file = service.files().get_media(fileId=file_item['id'])
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request_file)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            fh.seek(0)
            temp_pdf_path = None
            try:
                temp_dir = tempfile.gettempdir()
                temp_pdf_filename = f"temp_drive_pdf_{file_item['id']}_{os.urandom(4).hex()}.pdf"
                temp_pdf_path = os.path.join(temp_dir, temp_pdf_filename)
                with open(temp_pdf_path, 'wb') as f_temp:
                    f_temp.write(fh.getvalue())
                logger.info("Saved PDF content for %s to temporary file: %s", file_name, temp_pdf_path)
                logger.info("Running extraction pipeline for %s...", file_name)
                po_json_data_for_db = run_pipeline(temp_pdf_path)
                if po_json_data_for_db:
                    insert_or_replace_po(po_json_data_for_db)
                    logger.info("Successfully inserted/replaced PO data for %s into database.", file_name)
                    extracted_texts_summary.append(
                        f"Inserted/replaced PO data for: {file_name}")
                else:
                    logger.warning("No data extracted from %s. Skipping database insertion for this file.", file_name)
                    extracted_texts_summary.append(
                        f"No data extracted from {file_name}. DB insert skipped.")
            finally:
                if temp_pdf_path and os.path.exists(temp_pdf_path):
                    logger.info("Deleting temporary file: %s", temp_pdf_path)
                    os.remove(temp_pdf_path)
        except Exception as error:
            error_message = f"Error processing file {file_name} (ID: {file_id}): {error}"
            logger.error(error_message, exc_info=True)
            extracted_texts_summary.append(
                f"Error processing: {file_name} - {error}")
        finally:
            if fh:
                fh.close()
        pdf_files_found = True

    logger.info("Finished processing folder ID: %s", folder_id)
    logger.info("Exporting Data to JSON and CSV...")
    from extractor.export import export_all_pos_json, export_all_csvs
    export_all_pos_json()
    export_all_csvs()
    logger.info("Data Export Complete.")
    logger.info("Generating Financial Forecast...")
    from forecast_processor import run_forecast_processing
    run_forecast_processing(input_json_path="./output/purchase_orders.json")
    logger.info("Financial Forecast Generation Complete.")
    logger.info("All processes finished successfully!")

    if not pdf_files_found:
        message = f"No PDF files found in the specified folder '{folder_metadata.get('name')}' (ID: {folder_id})."
        logger.warning(message)
        return message
    else:
        response_message = f"PDF text extraction process initiated for folder '{folder_metadata.get('name')}' (ID: {folder_id}). Check your terminal for output. Summary of processed files:<br>"
        response_message += "<br>".join(extracted_texts_summary)
        logger.info("PDF text extraction summary for folder '%s': %s", folder_metadata.get('name'), extracted_texts_summary)
        return response_message


@app.route('/edit_po/<po_id>', methods=['GET', 'POST'])
@login_required
def edit_po(po_id):
    if request.method == 'POST':
        logger.info("Received POST request to edit PO '%s' by user '%s'", po_id, session.get('username'))
        # Normalize status to one of the allowed values
        raw_status = request.form.get('status', "").strip().lower()
        if raw_status == "confirmed":
            status = "Confirmed"
        elif raw_status == "unconfirmed":
            status = "Unconfirmed"
        else:
            status = "unspecified"
            logger.warning("Unknown status value received: '%s' (user: %s)", raw_status, session.get('username'))
        # Get the potentially new PO ID from the form
        new_po_id = request.form.get('po_id', po_id).strip()
        # Collect updated fields from the form
        po_data = {
            'po_id': new_po_id,
            'client_name': request.form.get('client_name'),
            'amount': float(request.form.get('amount')) if request.form.get('amount') else 0.0,
            'status': status,
            'payment_terms': int(request.form.get('payment_terms')) if request.form.get('payment_terms') else None,
            'payment_type': request.form.get('payment_type'),
            'start_date': request.form.get('start_date'),
            'end_date': request.form.get('end_date'),
            'duration_months': int(request.form.get('duration_months')) if request.form.get('duration_months') else None,
            'payment_frequency': int(request.form.get('payment_frequency')) if request.form.get('payment_frequency') else None,
            'project_owner': request.form.get('project_owner'),
        }
        logger.debug("PO data to update: %s", po_data)
        # Handle milestones and payment_schedule
        if po_data['payment_type'] == 'milestone':
            milestones = []
            names = request.form.getlist('milestone_name')
            descs = request.form.getlist('milestone_description')
            dues = request.form.getlist('milestone_due_date')
            pers = request.form.getlist('milestone_percentage')
            for n, d, due, p in zip(names, descs, dues, pers):
                if n and p:  # Only add milestone if name and percentage are provided
                    milestones.append({
                        'milestone_name': n,
                        'milestone_description': d or None,
                        'milestone_due_date': due or None,
                        'milestone_percentage': float(p) if p else 0.0
                    })
            po_data['milestones'] = milestones
            po_data['payment_schedule'] = []  # Clear payment schedule for milestone type
            logger.info("Processed milestones for PO %s: %s", po_data['po_id'], milestones)
        elif po_data['payment_type'] == 'distributed':
            schedule = []
            dates = request.form.getlist('payment_date')
            amounts = request.form.getlist('payment_amount')
            descs = request.form.getlist('payment_description')
            for dt, amt, desc in zip(dates, amounts, descs):
                if dt and amt:  # Only add payment if date and amount are provided
                    schedule.append({
                        'payment_date': dt,
                        'payment_amount': float(amt) if amt else 0.0,
                        'payment_description': desc or None
                    })
            po_data['payment_schedule'] = schedule
            po_data['milestones'] = []  # Clear milestones for distributed type
            logger.info("Processed distributed payment schedule for PO %s: %s", po_data['po_id'], schedule)
        else:  # periodic payment type
            po_data['milestones'] = []  # Clear milestones for periodic type
            po_data['payment_schedule'] = []  # Clear payment schedule for periodic type
            logger.info("Processed periodic payment type for PO %s", po_data['po_id'])
        # Save changes (will create new record if PO ID changed, or update existing)
        try:
            insert_or_replace_po(po_data)
            logger.info("Inserted/updated PO in database: %s (user: %s)", po_data['po_id'], session.get('username'))
            flash(f"Purchase Order '{po_data['po_id']}' updated successfully!", "success")
        except Exception as e:
            logger.error("Error inserting PO into database for user %s: %s", session.get('username'), e, exc_info=True)
            flash("Error saving purchase order.", "danger")
            return render_template('edit_po.html', po=po_data)
        # Regenerate forecast files after editing PO
        from extractor.export import export_all_pos_json, export_all_csvs
        from forecast_processor import run_forecast_processing
        try:
            export_all_pos_json()
            export_all_csvs()
            run_forecast_processing(input_json_path="./output/purchase_orders.json")
            logger.info("Exported all POs and ran forecast processing after PO edit (PO: %s, user: %s)", po_data['po_id'], session.get('username'))
        except Exception as e:
            logger.error("Warning: Could not regenerate forecast files after PO edit for PO %s by user %s: %s", po_data['po_id'], session.get('username'), e, exc_info=True)
        return redirect(url_for('forecast'))
    # GET: Show form with current PO data
    logger.info("Rendering edit PO form for PO ID '%s' (user: %s)", po_id, session.get('username'))
    po = get_po_with_schedule(po_id)
    if not po:
        logger.warning("PO with ID %s not found (user: %s)", po_id, session.get('username'))
        return f"<p>PO with ID {po_id} not found.</p>"
    return render_template('edit_po.html', po=po)


@app.route('/refresh_charts')
@login_required
def refresh_charts():
    logger.info("User '%s' triggered /refresh_charts to refresh charts and forecast.", session.get('username'))
    try:
        from extractor.export import export_all_pos_json, export_all_csvs
        from forecast_processor import run_forecast_processing
        logger.debug("Exporting all POs to JSON and CSV...")
        export_all_pos_json()
        export_all_csvs()
        logger.debug("Running forecast processing...")
        run_forecast_processing(input_json_path="./output/purchase_orders.json")
        logger.info("Successfully refreshed charts and forecast for user '%s'.", session.get('username'))
    except Exception as e:
        logger.error("Error refreshing charts/forecast for user '%s': %s", session.get('username'), e, exc_info=True)
        flash("Error refreshing charts/forecast.", "danger")
    return redirect(url_for('forecast'))


@app.route('/download_xlsx')
@login_required
def download_xlsx():
    logger.info("User '%s' triggered /download_xlsx to download the forecast pivot XLSX.", session.get('username'))
    try:
        from extractor.export import export_all_pos_json, export_all_csvs
        from forecast_processor import run_forecast_processing
        logger.debug("Exporting all POs to JSON and CSV before XLSX download...")
        export_all_pos_json()
        export_all_csvs()
        logger.debug("Running forecast processing before XLSX download...")
        run_forecast_processing(input_json_path="./output/purchase_orders.json")
        xlsx_path = os.path.abspath("forecast_pivot.xlsx")
        logger.info("Sending file '%s' to user '%s' as attachment.", xlsx_path, session.get('username'))
        return send_file(xlsx_path, as_attachment=True, download_name="forecast_pivot.xlsx")
    except Exception as e:
        logger.error("Error downloading XLSX for user '%s': %s", session.get('username'), e, exc_info=True)
        flash("Error downloading XLSX file.", "danger")
        return redirect(url_for('forecast'))


@app.route('/drive_folder_upload', methods=['GET', 'POST'])
@login_required
def drive_folder_upload():
    logger = setup_logger()
    logger.info("User '%s' accessed /drive_folder_upload.", session.get('username'))
    if 'credentials' not in session:
        logger.warning("No credentials in session for user: %s", session.get('username'))
        return redirect(url_for('authorize'))
    creds = Credentials.from_authorized_user_info(session['credentials'])
    service = build('drive', 'v3', credentials=creds)
    error = None
    pdf_files = []
    folder_id = None
    folder_url = ''
    llm_summary = None
    if request.method == 'POST':
        logger.info("Received POST request to /drive_folder_upload from user '%s'", session.get('username'))
        folder_url = request.form.get('folder_url', '').strip()
        folder_id = request.form.get('folder_id', '').strip()
        run_llm = request.form.get('run_llm')
        logger.debug("Form data: folder_url='%s', folder_id='%s', run_llm=%s", folder_url, folder_id, run_llm)
        # If folder_url is provided, extract folder_id from it
        if folder_url:
            import re
            match = re.search(r'/folders/([a-zA-Z0-9_-]+)', folder_url)
            if match:
                folder_id = match.group(1)
                logger.debug("Extracted folder_id '%s' from folder_url.", folder_id)
            else:
                folder_id = folder_url  # Assume user pasted the ID directly
                logger.debug("No folder_id extracted from URL, using as is: '%s'", folder_id)
        if folder_id:
            try:
                logger.info("Fetching metadata for folder_id='%s'", folder_id)
                folder_metadata = service.files().get(fileId=folder_id, fields="id, name, mimeType").execute()
                if folder_metadata.get('mimeType') != 'application/vnd.google-apps.folder':
                    error = f"The provided ID '{folder_id}' is not a folder."
                    logger.warning("Provided ID '%s' is not a folder (user: %s)", folder_id, session.get('username'))
                    folder_id = None
                else:
                    logger.info("Accessing folder: %s (ID: %s)", folder_metadata.get('name'), folder_id)
                    response = service.files().list(
                        q=f"'{folder_id}' in parents and trashed = false and mimeType = 'application/pdf'",
                        fields="files(id, name, modifiedTime)",
                    ).execute()
                    pdf_files = response.get('files', [])
                    logger.info("Found %d PDF files in folder '%s' (ID: %s)", len(pdf_files), folder_metadata.get('name'), folder_id)
                    # --- Store drive file details if Confirm Folder is clicked ---
                    if request.form.get('confirm_folder'):
                        logger.info("User '%s' confirmed folder '%s' (ID: %s)", session.get('username'), folder_metadata.get('name'), folder_id)
                        all_files_in_folder = list_all_files_in_folder(service, folder_id)
                        from db.crud import upsert_drive_files_sqlalchemy
                        upsert_drive_files_sqlalchemy(all_files_in_folder)
                        logger.info("Upserted %d files from Drive folder '%s' (ID: %s) into database.", len(all_files_in_folder), folder_metadata.get('name'), folder_id)
                    if run_llm and pdf_files:
                        logger.info("User '%s' initiated LLM extraction for folder '%s' (ID: %s)", session.get('username'), folder_metadata.get('name'), folder_id)
                        # --- Get all files in Drive (recursively) ---
                        all_files_in_folder = list_all_files_in_folder(service, folder_id)
                        pdfs = [f for f in all_files_in_folder if f.get('mimeType') == 'application/pdf']
                        extracted_texts_summary = []
                        # Get all files in DB (by file ID)
                        db_files = get_all_drive_files()  # {name: (last_edited, id)}
                        db_file_ids = set(db_id for (_, db_id) in db_files.values())
                        for file_item in pdfs:
                            file_name = file_item['name']
                            file_id = file_item['id']
                            # Only process if file_id not in DB
                            if file_id in db_file_ids:
                                logger.info("Skipped (already processed): %s", file_name)
                                extracted_texts_summary.append(f"Skipped (already processed): {file_name}")
                                continue
                            try:
                                logger.info("Downloading file '%s' (id=%s)", file_name, file_id)
                                request_file = service.files().get_media(fileId=file_id)
                                fh = io.BytesIO()
                                downloader = MediaIoBaseDownload(fh, request_file)
                                done = False
                                while not done:
                                    status, done = downloader.next_chunk()
                                fh.seek(0)
                                temp_pdf_path = None
                                try:
                                    temp_dir = tempfile.gettempdir()
                                    temp_pdf_filename = f"temp_drive_pdf_{file_id}_{os.urandom(4).hex()}.pdf"
                                    temp_pdf_path = os.path.join(temp_dir, temp_pdf_filename)
                                    with open(temp_pdf_path, 'wb') as f_temp:
                                        f_temp.write(fh.getvalue())
                                    logger.info("Saved PDF content for %s to temporary file: %s", file_name, temp_pdf_path)
                                    logger.info("Running extraction pipeline for %s...", file_name)
                                    po_json_data_for_db = run_pipeline(temp_pdf_path)
                                    if po_json_data_for_db:
                                        insert_or_replace_po(po_json_data_for_db)
                                        logger.info("Inserted/replaced PO data for: %s", file_name)
                                        extracted_texts_summary.append(f"Inserted/replaced PO data for: {file_name}")
                                    else:
                                        logger.warning("No data extracted from %s. DB insert skipped.", file_name)
                                        extracted_texts_summary.append(f"No data extracted from {file_name}. DB insert skipped.")
                                finally:
                                    if temp_pdf_path and os.path.exists(temp_pdf_path):
                                        logger.info("Deleting temporary file: %s", temp_pdf_path)
                                        os.remove(temp_pdf_path)
                            except Exception as error:
                                logger.error("Error processing file %s (ID: %s): %s", file_name, file_id, error, exc_info=True)
                                extracted_texts_summary.append(f"Error processing: {file_name} - {error}")
                            finally:
                                if fh:
                                    fh.close()
                        # --- Update drive_files table after processing ---
                        from db.crud import upsert_drive_files_sqlalchemy
                        upsert_drive_files_sqlalchemy(all_files_in_folder)
                        logger.info("Upserted %d files from Drive folder '%s' (ID: %s) after LLM extraction.", len(all_files_in_folder), folder_metadata.get('name'), folder_id)
                        from extractor.export import export_all_pos_json, export_all_csvs
                        from forecast_processor import run_forecast_processing
                        logger.info("Exporting all POs to JSON and CSV after LLM extraction...")
                        export_all_pos_json()
                        export_all_csvs()
                        logger.info("Running forecast processing after LLM extraction...")
                        run_forecast_processing(input_json_path="./output/purchase_orders.json")
                        logger.info("LLM extraction and forecast processing complete for folder '%s' (ID: %s)", folder_metadata.get('name'), folder_id)
                        llm_summary = extracted_texts_summary
            except Exception as e:
                logger.error("Invalid folder link or error accessing folder '%s': %s", folder_id, e, exc_info=True)
                error = f"Invalid folder link or error accessing folder: {e}"
                folder_id = None
    return render_template('drive_folder_upload.html', error=error, pdf_files=pdf_files, folder_id=folder_id, folder_url=folder_url, llm_summary=llm_summary)

def generate_unconfirmed_po_id():
    logger.debug("Generating new unconfirmed PO ID.")
    session = SessionLocal()
    try:
        count = session.query(PurchaseOrder).filter(PurchaseOrder.po_id.like("unconfirmed-%")).count()
        new_id = f"unconfirmed-{count + 1}"
        logger.info("Generated unconfirmed PO ID: %s", new_id)
        return new_id
    except Exception as e:
        logger.error("Error generating unconfirmed PO ID: %s", e, exc_info=True)
        raise
    finally:
        session.close()

@app.route("/submit-po", methods=["POST"])
@login_required
def submit_po():
    logger.info("User '%s' submitted a new PO via /submit-po.", session.get('username'))
    form = request.form
    logger.debug("Form data received: %s", dict(form))
    # Normalize status to one of the allowed values
    raw_status = form.get("status", "").strip().lower()
    if raw_status == "confirmed":
        status = "Confirmed"
    elif raw_status == "unconfirmed":
        status = "Unconfirmed"
    else:
        status = "unspecified"
        logger.warning("Unknown status value received: '%s' (user: %s)", raw_status, session.get('username'))
    po_dict = {
        "po_id": generate_unconfirmed_po_id(),
        "client_name": form.get("client_name"),
        "amount": form.get("amount"),
        "status": status,
        "payment_terms": form.get("payment_terms"),
        "payment_type": form.get("payment_type"),
        "start_date": form.get("start_date"),
        "end_date": form.get("end_date"),
        "duration_months": form.get("duration_months"),
        "payment_frequency": form.get("payment_frequency"),  # optional
    }
    logger.debug("Constructed PO dict: %s", po_dict)
    # Handle distributed payments
    if form.get("payment_type") == "distributed":
        payment_schedule = []
        for key in form.keys():
            if key.startswith("payment_date_"):
                index = key.split("_")[-1]
                date = form.get(f"payment_date_{index}")
                amount = form.get(f"payment_amount_{index}")
                if date and amount:
                    payment_schedule.append({"payment_date": date, "payment_amount": amount})
        po_dict["payment_schedule"] = payment_schedule
        logger.info("Processed distributed payment schedule for PO %s: %s", po_dict["po_id"], payment_schedule)
    # Handle milestones
    if form.get("payment_type") == "milestone":
        milestones = []
        total_percentage = 0.0
        for key in form:
            if key.startswith("milestone_name_"):
                index = key.split("_")[-1]
                try:
                    percent = float(form.get(f"milestone_percent_{index}", 0))
                except ValueError:
                    percent = 0
                    logger.warning("Invalid milestone percent for index %s (user: %s)", index, session.get('username'))
                total_percentage += percent
                milestones.append({
                    "milestone_name": f"Milestone {index}",
                    "milestone_description": form.get(f"milestone_description_{index}"),
                    "milestone_due_date": form.get(f"milestone_due_{index}"),
                    "milestone_percentage": form.get(f"milestone_percent_{index}"),
                })
        if round(total_percentage, 2) != 100.00:
            logger.error("Milestone percentages do not add up to 100%% (got %.2f) for PO %s by user %s", total_percentage, po_dict["po_id"], session.get('username'))
            flash("❌ Milestone percentages must add up to 100%.", "danger")
            return render_template("add_unconfirmed_order.html", form_data=request.form)
        po_dict["milestones"] = milestones
        logger.info("Processed milestones for PO %s: %s", po_dict["po_id"], milestones)
    # Insert into DB
    try:
        insert_or_replace_po(po_dict)
        logger.info("Inserted/updated PO in database: %s (user: %s)", po_dict["po_id"], session.get('username'))
    except Exception as e:
        logger.error("Error inserting PO into database for user %s: %s", session.get('username'), e, exc_info=True)
        flash("Error saving purchase order.", "danger")
        return render_template("add_unconfirmed_order.html", form_data=request.form)
    return redirect(url_for("forecast")) 


@app.route("/delete-po/<po_id>", methods=["POST"])
@login_required
def delete_po(po_id): 
    logger.info("User '%s' requested deletion of PO '%s' via /delete-po.", session.get('username'), po_id)
    session_db = SessionLocal()
    try:
        po = session_db.query(PurchaseOrder).filter_by(po_id=po_id).first()
        if not po:
            logger.warning("No purchase order found with ID '%s' for user '%s'", po_id, session.get('username'))
            flash(f"❌ No purchase order found with ID '{po_id}'", "danger")
            return redirect(url_for("dashboard"))
        logger.info("Found PO '%s' for deletion. Type: %s", po_id, po.payment_type)
        if po.payment_type == "milestone":
            logger.debug("Deleting milestones for PO '%s'", po_id)
            session_db.query(Milestone).filter_by(po_id=po_id).delete()
        elif po.payment_type == "periodic":
            logger.debug("Deleting periodic payments for PO '%s'", po_id)
            session_db.query(PaymentSchedule).filter_by(po_id=po_id).delete()
        elif po.payment_type == "distributed":
            logger.debug("Deleting distributed payments for PO '%s'", po_id)
            session_db.query(PaymentSchedule).filter_by(po_id=po_id).delete()       
        session_db.delete(po)
        session_db.commit()
        logger.info("Successfully deleted PO '%s' for user '%s'", po_id, session.get('username'))
        flash(f"✅ Purchase Order '{po_id}' deleted successfully.", "success")
    except Exception as e:
        session_db.rollback()
        logger.error("Error deleting PO '%s' for user '%s': %s", po_id, session.get('username'), e, exc_info=True)
        flash(f"❌ Error deleting PO: {str(e)}", "danger")
    finally:
        session_db.close()
    return redirect(url_for("forecast"))


@app.route("/backup-now", methods=["POST"])
@login_required
def backup_now():   
    import os
    import subprocess
    from flask import current_app
    try:
        project_root = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(project_root, "backup_and_upload.sh")
        logger.info("User '%s' initiated backup via /backup-now. Script: %s", session.get('username'), script_path)
        result = subprocess.run(
            [script_path],
            capture_output=True,
            text=True,
            check=True
        )
        logger.info("Backup completed successfully. Output: %s", result.stdout)
        flash("✅ Backup completed successfully.", "success")
    except subprocess.CalledProcessError as e:
        logger.error("Backup failed. Return code: %s, Error: %s, Output: %s", e.returncode, e.stderr, e.output, exc_info=True)
        flash(f"❌ Backup failed: {e.stderr}", "danger")
    except Exception as e:
        logger.error("Unexpected error during backup: %s", e, exc_info=True)
        flash(f"❌ Backup failed: {e}", "danger")
    return redirect(url_for("forecast"))  

@app.route("/restore", methods=["POST"])
def restore_backup():
    import os
    import subprocess
    from flask import current_app
    try:
        project_root = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(project_root, "restore_backup.sh")
        logger.info("Restore initiated via /restore. Script: %s", script_path)
        result = subprocess.run(
            [script_path],
            capture_output=True,
            text=True,
            check=True
        )
        logger.info("Restore completed successfully. Output: %s", result.stdout)
        flash("✅ Restore completed successfully.", "success")
    except subprocess.CalledProcessError as e:
        logger.error("Restore failed. Return code: %s, Error: %s, Output: %s", e.returncode, e.stderr, e.output, exc_info=True)
        flash(f"❌ Restore failed:\n{e.stderr}", "danger")
    except Exception as e:
        logger.error("Unexpected error during restore: %s", e, exc_info=True)
        flash(f"❌ Restore failed: {e}", "danger")
    return redirect(url_for("forecast"))

if __name__ == '__main__':
    init_db()
    app.run(host="0.0.0.0", debug=True)
